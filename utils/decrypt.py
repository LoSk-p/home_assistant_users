from substrateinterface import KeypairType, Keypair
from robonomicsinterface import Account
from requests import get
import json
from conf import LAUNCH_SEED, LAUNCH_CONTROLLER_ADDRESS, URL_TO_READ


def decrypt_message(encrypted_message: str, sender_public_key: bytes, recipient_keypair: Keypair) -> str:
    """Decrypt message with recepient private key and sender puplic key

    :param encrypted_message: Message to decrypt
    :param sender_public_key: Sender public key
    :param recipient_keypair: Recepient account keypair

    :return: Decrypted message
    """

    if encrypted_message[:2] == "0x":
        encrypted_message = encrypted_message[2:]
    bytes_encrypted = bytes.fromhex(encrypted_message)

    return recipient_keypair.decrypt_message(bytes_encrypted, sender_public_key)

def main():
    print(f"Get request to {URL_TO_READ}")
    resp = get(URL_TO_READ)
    print(f"Response: {resp.status_code}")
    encrypted = resp.text

    sender = Account(LAUNCH_SEED, crypto_type=KeypairType.ED25519)
    recepient = Keypair(ss58_address=LAUNCH_CONTROLLER_ADDRESS, crypto_type=KeypairType.ED25519)
    message = decrypt_message(encrypted, sender.keypair.public_key, sender.keypair)
    message = message.decode("utf-8")
    with open("decrypted", "w") as f:
        f.write(message)
    json_message = json.loads(message)
    return json_message

main()