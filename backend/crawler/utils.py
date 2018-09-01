import re
import logging
import paramiko
from threading import Thread


class SSHClient(paramiko.client.SSHClient):
    def __init__(self, ip, username, password, *args):
        self.ip = ip
        self.username = username
        self.password = password
        self.fid_list = list()
        super().__init__(*args)
        self.set_missing_host_key_policy(
            paramiko.client.AutoAddPolicy()
        )

    def connect(self):
        try:
            super().connect(
                self.ip,
                username=self.username,
                password=self.password,
                timeout=20
            )
            return True
        except paramiko.ssh_exception.AuthenticationException:
            logging.error('wrong credential')
            return False
        except paramiko.ssh_exception.SSHException:
            return False


class CiscoSwitch(SSHClient):
    def __init__(self, *args, **kwargs):
        self.vendor = 'cisco'
        self.fcns = ''
        super().__init__(*args, **kwargs)
        self.connect()
        self._get_fcns_database()

    def _get_fcns_database(self):
        """
        This function dumps fcns databse from the Cisco Switch.
        """
        command = 'show fcns database detail'
        try:
            self.fcns = self.exec_command(command)[1].read().decode()
        except paramiko.ssh_exception.SSHException:
            logging.error(f'failed to get fcns database from {self.ip}')

    def get_wwpn_location(self):
        """
        This function analyzes fcns database and retuns a generator which yield
        a dict once a time for each WWPN discovered in the fabric.
        """

        def _analyze_record(raw):
            wwpn_pattern = r'\w{2}(:\w{2}){7}'
            record = {}
            if 'VSAN' not in raw:
                return {}
            for line in raw.split('\n'):
                if line.startswith('port-wwn'):
                    try:
                        record.update(wwpn=re.search(wwpn_pattern, line).group())
                    except AttributeError:
                        # no wwpn means no record
                        return {}

                elif 'VSAN:' in line:
                    record.update(vsan=line.split(':')[1].split()[0])
                elif 'connected interface' in line:
                    record.update(port=line.split(':')[-1].strip())
                elif 'switch name (IP address)' in line:
                    switch_name_and_ip = line.split(':')[-1].strip()
                    if '(' in switch_name_and_ip:
                        record.update(switch_ip=switch_name_and_ip.split('(')[-1].split(')')[0])
                        record.update(switchname=switch_name_and_ip.split('(')[0].strip())
                    else:
                        record.update(switch_ip='')
                        record.update(switch_name=switch_name_and_ip)
            return record

        if not self.fcns:
            return None
        for block in re.split('-{24}(?=\nVSAN)', self.fcns):
            record = _analyze_record(block)
            if record:
                yield record


class BrocadeSwitch(SSHClient):
    def __init__(self, *args, **kwargs):
        self.vendor = 'brocade'
        self.fid_list = list()
        self.vswitches = list()
        super().__init__(*args, **kwargs)
        self.connect()

    def _get_fid_list(self):
        possible_cmd = [
            "configshow -all | grep 'Fabric ID'",
            "configshow | grep 'Fabric ID'"
        ]
        fid_list = []
        for cmd in possible_cmd:
            output = self._get_command_output(cmd)
            if output:
                fid_list += re.findall(r'\d+', output)
        self.fid_list = fid_list

    def _spawn_vswitch(self):
        self._get_fid_list()
        for fid in self.fid_list:
            self.vswitches.append(BrocadeVirtualSwitch(self.ip, self.username, self.password, fid))

    def _get_command_output(self, command, fid=None):
        """
        This function helps to get the output of a command as a string.
        """
        if fid:
            command = f'fosexec --fid {fid} -cmd {command}'
        try:
            _, o, e = self.exec_command(command)
        except paramiko.ssh_exception.SSHException as error:
            logging.warning(error)
            logging.warning(f'failed to run {command}')
            return None

        error = e.read()
        if error:
            logging.warning(f'Got error message {error.decode()} from \n{command}')
            return None
        output = o.read()
        if output:
            return output.decode()
        return None

    def get_wwpn_location(self):
        self._spawn_vswitch()
        locations = list()
        threads = list()
        for vswitch in self.vswitches:
            t = Thread(target=vswitch.get_wwpn_location)
            threads.append(t)
            t.start()
        for x in threads:
            x.join()
        for vswitch in self.vswitches:
            locations += vswitch.all_wwpn
        return locations

class BrocadeVirtualSwitch(BrocadeSwitch):
    def __init__(self, ip, username, password, fid, **kwargs):
        self.wwpn_pattern = r'\w{2}(:\w{2}){7}'
        self.fid = fid
        self.switchshow = ''
        self.switchname = ''
        self.fabricshow = ''
        self.fabric_members = list()
        self.local_wwpn = list()
        self.all_wwpn = list()
        super().__init__(ip, username, password, **kwargs)
        self.connect()

    def _get_command_output(self, command):
        return super()._get_command_output(command, fid=self.fid)

    def _get_switch_name(self):
        for line in self.switchshow.split("\n"):
            if line.startswith('switchName:'):
                self.switchname = line.split(":")[-1].strip()

    def _get_switchshow(self):
        raw = self._get_command_output('switchshow')
        if raw:
            self.switchshow = raw
        else:
            logging.error(f'unable to get switchshow of {self.ip}')

    def _get_fabricshow(self):
        raw = self._get_command_output('fabricshow')
        if raw:
            self.fabricshow = raw
        else:
            logging.error(f'unable to get fabricshow of {self.ip}')

    def _get_fabric_members(self):
        raw = self._get_command_output('fabricshow')
        if raw:
            raw = raw.split('-\n')[-1]
            for line in raw.split('\n'):
                if ":" in line:
                    self.fabric_members.append(line.split()[3])

    def get_flogin_wwpn(self):
        """
        retrive flogin wwpn from switchshow
        """
        self._get_switchshow()
        self._get_switch_name()
        for line in self.switchshow.split('===\n')[-1].split('\n'):
            if 'Online' not in line:
                continue
            port_index = line.split()[0]
            wwpn_search = re.search(self.wwpn_pattern, line)
            if wwpn_search:
                self.local_wwpn.append(
                    dict(
                        port_index=port_index,
                        wwpn=wwpn_search.group(),
                        switch_name=self.switchname,
                        switch_ip=self.ip,
                        fid=self.fid
                    )
                )

    def get_wwpn_location(self):
        """
        This generator yields other generators who yield the actual wwpn records
        """
        self._get_fabricshow()
        self._get_fabric_members()
        threads = list()
        member_switches = list()
        for member in self.fabric_members:
            member_switch = BrocadeVirtualSwitch(member, self.username, self.password, self.fid)
            t = Thread(target=member_switch.get_flogin_wwpn)
            threads.append(t)
            member_switches.append(member_switch)
            t.start()
        for x in threads:
            x.join()
        for member_switch in member_switches:
            self.all_wwpn += member_switch.local_wwpn
