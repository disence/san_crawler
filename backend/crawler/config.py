from utils import BrocadeSwitch, CiscoSwitch

cisco = [
    ('10.228.99.131', 'emc', 'Emc12345'),
]

brocade = [
    ('10.228.99.11', 'emc', 'Elab0123'),
]

mongo = {
    "host": "10.228.107.11",
    "port": 32768,
    "db": "wwpn_info",
    "collection": "locations"
}

interval = 60
