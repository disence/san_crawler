from lib import BrocadeSwitch, CiscoSwitch

search_scope = [
    # take the following lines as an example
    CiscoSwitch('10.228.104.13', 'emc', 'Emc12345'),
    BrocadeSwitch('10.228.96.102', 'user_vplexa', 'password'),  # FID 5
    BrocadeSwitch('10.228.96.102', 'user_vplexb', 'password'),  # FID 10
    BrocadeSwitch('10.228.183.12', 'user_platform', 'password'),  # FID 40
    BrocadeSwitch('10.103.116.46', 'cd', 'password'),  # FID 98
    BrocadeSwitch('10.103.116.15', 'user_symmetrix', 'password'),  # FID 128
]
