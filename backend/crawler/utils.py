import re
import logging
import paramiko
from threading import Thread
from itertools import chain


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
        super().__init__(*args, **kwargs)
        self.connect()

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

    def get_fid_list(self):
        self.fid_list = list()
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

class BrocadeVirtualSwitch(BrocadeSwitch):
    def __init__(self, ip, username, password, fid, **kwargs):
        self.wwpn_pattern = r'\w{2}(:\w{2}){7}'
        self.fid = fid
        self.switchshow = ''
        self.switchname = ''
        self.fabricshow = ''
        self.fabricmap = list()
        super().__init__(ip, username, password, **kwargs)
        self._get_switchshow()
        self._get_fabricshow()
        self._get_nscamshow()
        self._get_switchname()
        self._get_fabricmap()


    def _get_command_output(self, command):
        return super()._get_command_output(command, fid=self.fid)

    def _get_switchshow(self):
        self.switchshow = self._get_command_output('switchshow')

    def _get_fabricshow(self):
        self.fabricshow = self._get_command_output('fabricshow')

    def _get_nscamshow(self):
        self.nscamshow= self._get_command_output('nscamshow')

    def _get_switchname(self):
        for line in self.switchshow.split("\n"):
            if line.startswith('switchName:'):
                self.switchname = line.split(":")[-1].strip()

    def _get_fabricmap(self):
        for line in self.fabricshow.split('-\n')[-1].split('\n'):
            if ':' in line:
                items = line.split()
                self.fabricmap.append(
                    dict(
                        switch_id=items[1],
                        switch_ip=items[3],
                        switch_name=items[5].strip('>" ')
                    )
                )

    def get_plogin_wwpn(self):
        """
Example of the nscamshow:
    N    172a07;    2,3;c0:50:76:05:09:6b:00:66;c0:50:76:05:09:6b:00:66;
        Fabric Port Name: 20:2e:00:05:33:69:62:02
        Permanent Port Name: 10:00:00:00:c9:a1:82:bd
        Port Index: 46
        Share Area: No
        Device Shared in Other AD: No
        Redirect: No
        Partial: No
    N    172a08;    2,3;c0:50:76:05:09:6b:00:72;c0:50:76:05:09:6b:00:72;
        Fabric Port Name: 20:2e:00:05:33:69:62:02
        Permanent Port Name: 10:00:00:00:c9:a1:82:bd
        Port Index: 46
        Share Area: No
        Device Shared in Other AD: No
        Redirect: No
        Partial: No
        """
        for n in self.nscamshow.split("\n"):
            if re.match(r"\s+N\s+", n):
                (fc_id, _, wwpn, *__) = n.split(";")
                switch_id = fc_id.split()[1][0:2]
                for i in self.fabricmap:
                    if i["switch_id"].endswith(switch_id):
                        break
            if "Port Index:" in n:
                port_index = re.search(r"\d+", n).group()
                yield dict(
                    port_index=port_index,
                    wwpn=wwpn,
                    switch_name=i["switch_name"],
                    switch_ip=i["switch_ip"],
                    fid=self.fid
                )

    def get_flogin_wwpn(self):
        """
        retrive flogin wwpn from switchshow
        """
        for line in self.switchshow.split('===\n')[-1].split('\n'):
            if 'Online' not in line:
                continue
            port_index = line.split()[0]
            wwpn_search = re.search(self.wwpn_pattern, line)
            if wwpn_search:
                yield dict(
                    port_index=port_index,
                    wwpn=wwpn_search.group(),
                    switch_name=self.switchname,
                    switch_ip=self.ip,
                    fid=self.fid
                )
    def get_all_wwpn(self):
        return chain(
            self.get_flogin_wwpn(),
            self.get_plogin_wwpn()
        )
