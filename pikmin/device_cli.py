"""Device CLI with a validated local pairing fallback for stale usbmux records."""
import runpy


async def validate_with_local(client, original, read_local):
    if await original(client):
        return True
    record = read_local(client.identifier, client.pairing_records_cache_folder)
    if not record or record == client.pair_record:
        return False
    previous = client.pair_record
    client.pair_record = record
    try:
        if await original(client):
            return True
    except Exception:
        client.pair_record = previous
        raise
    client.pair_record = previous
    return False


def main():
    from pymobiledevice3.lockdown import UsbmuxLockdownClient
    from pymobiledevice3.pair_records import get_local_pairing_record
    original = UsbmuxLockdownClient.validate_pairing

    async def validate(client):
        return await validate_with_local(client, original, get_local_pairing_record)

    UsbmuxLockdownClient.validate_pairing = validate
    try:
        runpy.run_module('pymobiledevice3', run_name='__main__')
    finally:
        UsbmuxLockdownClient.validate_pairing = original


if __name__ == '__main__':
    main()
