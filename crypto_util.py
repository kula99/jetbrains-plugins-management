import rsa
from rsa import core, transform, PublicKey, PrivateKey


def decrypt(pubkey_file, prikey_file, cipher_text_bytes):
    with open(pubkey_file, 'rb') as f1, open(prikey_file, 'rb') as f2:
        pub_key = PublicKey.load_pkcs1(f1.read())
        pri_key = PrivateKey.load_pkcs1(f2.read())

    cipher_int = transform.bytes2int(cipher_text_bytes)
    decrypt_pub_int = core.decrypt_int(cipher_int, pub_key.e, pub_key.n)
    decrypt_pub_bytes = transform.int2bytes(decrypt_pub_int)
    plain_text_bytes = rsa.decrypt(decrypt_pub_bytes[decrypt_pub_bytes.index(0) + 1:], pri_key)
    return plain_text_bytes.decode()
