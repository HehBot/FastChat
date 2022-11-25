import rsa
from Crypto.Cipher import AES
import base64

import json

def pub_key_to_str(pub_key: rsa.key.PublicKey) -> str:
    """Converts public key to a string

    :param pub_key: Public key
    :type pub_key: rsa.key.PublicKey
    :return: Converted string
    :rtype: str
    """
    def tmp(x):
        return base64.b64encode(x.to_bytes((x.bit_length() + 7) // 8, byteorder='big')).decode("utf-8")
    return tmp(pub_key.n) + '-' + tmp(pub_key.e)

def str_to_pub_key(s: str) -> rsa.key.PublicKey:
    """Converts string to a public key

    :param s: Public key string
    :type s: str
    :return: Public key
    :rtype: rsa.key.PublicKey
    """
    def tmp(y):
        t = base64.b64decode(y)
        return int.from_bytes(t, 'big')
    s = s.split('-')
    s = tuple([tmp(x) for x in s])
    return rsa.PublicKey(*s)

def priv_key_to_str(priv_key: rsa.key.PrivateKey) -> str:
    """Converts private key to a string

    :param pub_key: Private key
    :type pub_key: rsa.key.PrivateKey
    :return: Converted string
    :rtype: str
    """
    def tmp(x):
        return base64.b64encode(x.to_bytes((x.bit_length() + 7) // 8, byteorder='big')).decode("utf-8")
    s = ""
    attrs = "nedpq"
    for c in attrs:
        s += tmp(getattr(priv_key, c)) + '-'
    return s[:-1]

def str_to_priv_key(s: str) -> rsa.key.PrivateKey:
    """Converts string to a private key

    :param s: Private key string
    :type s: str
    :return: Priavte key
    :rtype: rsa.key.PrivateKey
    """
    def tmp(y):
        t = base64.b64decode(y)
        return int.from_bytes(t, 'big')
    s = s.split('-')
    s = tuple([tmp(x) for x in s])
    return rsa.PrivateKey(*s)

class AESCipher(object):
    """This class is used for easy padded AES encryption

    :param bs: AES block size
    :type bs: int
    :param key: AES key that will be used
    :type key: rsa.hash
    """
    def __init__(self, key):
        self.bs = AES.block_size
        self.key = rsa.compute_hash(key, 'SHA-256')
    def encrypt(self, raw: str) -> str:
        raw = self._pad(raw)
        iv = rsa.randnum.read_random_bits(self.bs * 8)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return base64.b64encode(iv + cipher.encrypt(raw.encode())).decode("utf-8")
    def decrypt(self, enc: str) -> str:
        enc = base64.b64decode(enc)
        iv = enc[:self.bs]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return self._unpad(cipher.decrypt(enc[self.bs:])).decode("utf-8")
    def _pad(self, s: str) -> str:
        return s + (self.bs - len(s) % self.bs) * chr(self.bs - len(s) % self.bs)
    @staticmethod
    def _unpad(s: bytes) -> bytes:
        return s[:-ord(s[len(s)-1:])]

def encrypt_e2e_req(req: dict, recip_pub_key: rsa.key.PublicKey, sndr_priv_key: rsa.key.PrivateKey, aes_key_len: int = 128) -> str:
    """Encrypts a json message without encrypting the header
    
    :param req: JSON to be encrypted
    :type req: dict
    :param recip_pub_key: Recipient's public key 
    :type recip_pub_key: rsa.key.PublicKey
    :param sndr_priv_key: Sender's privte key 
    :type sndr_pub_key: rsa.key.PrivateKey
    :param aes_key_len: Length of AES key
    :type aes_key_len: int
    :return: Encrypted message
    :rtype: str
    """
    msg = req["msg"]
    time = req["time"]

    aes_key = rsa.randnum.read_random_bits(aes_key_len)
    aes = AESCipher(aes_key)

    enc_msg = aes.encrypt(msg)
    enc_aes_key = base64.b64encode(rsa.encrypt(aes_key, recip_pub_key)).decode("utf-8")
    enc_time = aes.encrypt(time)

    if "file" in req.keys():
        enc_file = aes.encrypt(req["file"])
        enc_msg = enc_msg + ' ' + enc_file

    comp_msg = req["hdr"] + enc_msg + enc_aes_key + enc_time
    sign = base64.b64encode(rsa.sign(comp_msg.encode("utf-8"), sndr_priv_key, "SHA-256")).decode("utf-8")

    return json.dumps({ "hdr":req["hdr"], "msg":enc_msg, "aes_key":enc_aes_key, "time":enc_time, "sign":sign })

def verify_e2e_req(req: dict, sndr_pub_key: rsa.key.PublicKey) -> bool:
    """Verifies signature of a request created using encrypt_e2e_req

    :param req: The request
    :type req: dict
    :param sndr_pub_key: Sender's public key
    :type sndr_pub_key: rsa.key.PublicKey
    :return: Whether request signature is valid
    :rtype: bool
    """
    try:
        rsa.verify((req["hdr"] + req["msg"] + req["aes_key"] + req["time"]).encode("utf-8"), base64.b64decode(req["sign"]), sndr_pub_key)
        return True
    except rsa.pkcs1.VerificationError:
        return False

def decrypt_e2e_req(json_string: str, recip_priv_key: rsa.key.PrivateKey, sndr_pub_key: rsa.key.PublicKey):
    """Decrypts json string produced by encrypting request using encrypt_e2e_req
    
    :param req_string: The JSON string to be decrypted
    :type req_string: str
    :param recip_priv_key: Private key of the recipient
    :type recip_priv_key: rsa.key.PrivateKey
    :param sndr_pub_key: Public key of the sender
    :type sndr_pub_key: rsa.key.PublicKey
    :return: Decrypted request
    :rtype: dict
    """
    req = json.loads(json_string)
    
    if not verify_e2e_req(req, sndr_pub_key):
        print("Signature mismatch")
        return

    aes_key = rsa.decrypt(base64.b64decode(req["aes_key"]), recip_priv_key)
    aes = AESCipher(aes_key)

    s = req["msg"].split()

    msg = aes.decrypt(s[0])
    time = aes.decrypt(req["time"])

    ret = { "hdr":req["hdr"], "msg":msg, "time":time }
    file = ""
    if len(s) == 2:
        file = aes.decrypt(s[1])
        ret["file"] = file

    return ret

def create_onboarding_req(uname: str, time: float, sndr_pub_key: rsa.key.PublicKey, sndr_priv_key: rsa.key.PrivateKey) -> str:
    """Create onboarding request that returning client sends to server

    :param uname: Username
    :type uname: str
    :param time: Timestamp
    :type time: float
    :param sndr_pub_key: Sender's public key
    :type sndr_pub_key: rsa.key.PublicKey
    :param sndr_priv_key: Sender's private key
    :type sndr_priv_key: rsa.key.PrivateKey
    :return: Onbarding request
    :rtype: str
    """
    hdr = "onboarding"
    
    msg = uname + ' ' + str(time)
    sign = base64.b64encode(rsa.sign((hdr + msg).encode("utf-8"), sndr_priv_key, "SHA-256")).decode("utf-8")

    return json.dumps({ "hdr":hdr, "msg":msg, "sign":sign })

def verify_onboarding_req(json_string, pub_key) -> bool:
    """Verify signature of request created using create_onboarding_req
    
    :param json_string: JSON string to be verified
    :type json_string: str
    :param pub_key: Public key of signer
    :type pub_key: rsa.key.PublicKey
:param recip_pub_key: The public key    :return: Whether request signature is valid
    :rtype: bool
    """
    req = json.loads(json_string)
    
    try:
        rsa.verify((req["hdr"] + req["msg"]).encode("utf-8"), base64.b64decode(req["sign"]), pub_key)
    except rsa.pkcs1.VerificationError:
        print("Signature mismatch")
        return False
    return True

def create_registering_req(uname: str, time: float, sndr_pub_key: rsa.key.PublicKey, sndr_priv_key: rsa.key.PrivateKey) -> str:
    """Create registering request that first time client sends to server
    
    :param uname: Username
    :type uname: str
    :param time: Timestamp
    :type time: float
    :param sndr_pub_key: Sender's public key
    :type sndr_pub_key: rsa.key.PublicKey
    :param sndr_priv_key: Sender's private key
    :type sndr_priv_key: rsa.key.PrivateKey
    :return: Registering request
    :rtype: str
    """
    hdr = "registering"

    msg = uname + ' ' + pub_key_to_str(sndr_pub_key) + ' ' + str(time)
    sign = base64.b64encode(rsa.sign((hdr + msg).encode("utf-8"), sndr_priv_key, "SHA-256")).decode("utf-8")

    return json.dumps({ "hdr":hdr, "msg":msg, "sign":sign })

def verify_registering_req(json_string: str) -> bool:
    """Verify signature of request created using create_registering_req
    
    :param json_string: JSON string to be verified
    :type json_string: str
    :param pub_key: Public key of signer
    :type pub_key: rsa.key.PublicKey
    :return: Whether request signature is valid
    :rtype: bool
    """
    req = json.loads(json_string)
    pub_key = str_to_pub_key(req["msg"].split()[1])

    try:
        rsa.verify((req["hdr"] + req["msg"]).encode("utf-8"), base64.b64decode(req["sign"]), pub_key)
    except rsa.pkcs1.VerificationError:
        print("Signature mismatch")
        return False
    return True
