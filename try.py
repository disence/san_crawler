import asyncio, asyncssh

async def run_command(command):
    async with asyncssh.connect(
    '45.76.96.156',
    username='root',
    client_keys=['C:/Users/ssung/Dropbox/My_Droplets/droplet_openssh']
    ) as conn:
        result = await conn.run(command)
        print(result.stdout)

TASKS = [run_command('ls'), run_command('ps;sleep 10')]

the_loop = asyncio.get_event_loop()
the_loop.run_until_complete(
    asyncio.wait(TASKS)
)
the_loop.run_until_complete(
    asyncio.wait([run_command('uptime')])
)
