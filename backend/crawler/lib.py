import re
import paramiko
import logging


class SSHClient(paramiko.client.SSHClient):
    def __init__(self, ip, username, password, *args):
        self.ip = ip
        self.username = username
        self.password = password
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

    def get_fcns_database(self):
        """
        This function dumps fcns databse from the Cisco Switch.
        """
        command = 'show fcns database detail'
        try:
            self.fcns = self.exec_command(command)[1].read().decode()
        except paramiko.ssh_exception.SSHException:
            logging.info(f'failed to get fcns database from {self.ip}')
            self.fcns = ''

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

        for block in re.split('-{24}(?=\nVSAN)', self.fcns):
            record = _analyze_record(block)
            if record:
                yield record


class BrocadeSwitch(SSHClient):
    def __init__(self, *args):
        self.vendor = 'brocade'
        self.get_switchshow = self.collect('switchshow')
        self.get_nscamshow = self.collect('nscamshow')
        self.get_fabricshow = self.collect('fabricshow')
        self.filter_local_fid = self.make_single_filter(
            r'(?<=FID: )\d+',
            description="""
            filter fid from switchshow
            """
            )
        self.filter_local_switchname = self.make_single_filter(
            '(?<=switchName:).+',
            description="""
            filter switchname from switchshow
            """
            )
        self.filter_wwpn = self.make_single_filter(
            '[0-9a-z:]{2}(:[0-9a-z:]{2}){7}',
            description="""
            filter out single wwpn from content
            """
            )

        super().__init__(*args)

    def collect(self, command, description=''):
        def inner(fid=''):
            if fid:
                full_command = 'fosexec --fid {} -cmd {}'.format(fid, command)
            else:
                full_command = command
            i, o, e = self.exec_command(full_command)
            try:
                return o.read().decode()
            except:
                logging.info(
                    'failed to read output of {} on {}'.format(
                        full_command, self.ip
                    )
                )
                return ''
        inner.__doc__ = description
        return inner

    def make_single_filter(self, f_content, description=''):
        def inner(content):
            pattern = re.compile(f_content)
            result_obj = re.search(pattern, content)
            if result_obj:
                result = result_obj.group()
                if isinstance(result, str):
                    return result.strip()
            logging.error(
                'failed to filter {} from {}'.format(pattern, content)
            )

            return None
        inner.__doc__ = description
        return inner

    def fabric_analyze(self, fabricshow):
        """
        return a fabric map in dict for plogin part
        """
        fabric_map = dict()
        content = fabricshow.split('-\n')[-1]
        for line in content.split('\n'):
            line = line.strip()
            items = re.split('\s+', line)
            if len(items) == 6:
                fabric_map[items[1]] = dict()  # use switch ID as key
                fabric_map[items[1]]['ip'] = items[3]
                fabric_map[items[1]]['name'] = items[5].strip('>" ')
        return fabric_map

    def plogin_wwpn(self, nscamshow, fabric_map):
        """
        retrive plogin wwpn from nscam
        return a generator of wwpn info in following format:
            [
            wwpn,
            port_index,
            switch_name,
            switch_ip
            ]
        """
        for n in nscamshow.split("\n"):
            if re.match("\s+N\s+", n):
                (switch_id, _, wwpn, *__) = n.split(";")
                switch_id = switch_id.split()[1][0:2]
                for full_id in fabric_map.keys():
                    if full_id.endswith(switch_id):
                        break
            if "Port Index:" in n:
                port_index = re.search("\d+", n).group()
                yield [
                    wwpn,
                    port_index,
                    fabric_map[full_id]['name'],
                    fabric_map[full_id]['ip']
                ]

    def flogin_wwpn(self, switchshow):
        """
        retrive flogin wwpn from switchshow
        return a generator of wwpn info in following format:
            [
            wwpn,
            port_index
            ]
        """
        for line in switchshow.split('===\n')[-1].split('\n'):
            if 'Online' not in line:
                continue
            port_index = line.split()[0]
            wwpn = self.filter_wwpn(line)
            if wwpn:
                yield [
                    wwpn,
                    port_index,
                ]

    def get_fid_list(self):
        possible_cmd = [
            "configshow -all | grep 'Fabric ID'",
            "configshow | grep 'Fabric ID'"
        ]
        fid_list = []
        for cmd in possible_cmd:
            i, o, e = self.exec_command(cmd)
            fid_list += re.findall('\d+', o.read().decode())
        return fid_list
