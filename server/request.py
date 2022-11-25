import rsa
from Crypto.Cipher import AES
import base64

import json

def pub_key_to_str(pub_key):
    def tmp(x):
        return base64.b64encode(x.to_bytes((x.bit_length() + 7) // 8, byteorder='big')).decode("utf-8")
    return tmp(pub_key.n) + '-' + tmp(pub_key.e)

def str_to_pub_key(s):
    def tmp(y):
        t = base64.b64decode(y)
        return int.from_bytes(t, 'big')
    s = s.split('-')
    s = tuple([tmp(x) for x in s])
    return rsa.PublicKey(*s)

def priv_key_to_str(priv_key):
    def tmp(x):
        return base64.b64encode(x.to_bytes((x.bit_length() + 7) // 8, byteorder='big')).decode("utf-8")
    s = ""
    attrs = "nedpq"
    for c in attrs:
        s += tmp(getattr(priv_key, c)) + '-'
    return s[:-1]

def str_to_priv_key(s):
    def tmp(y):
        t = base64.b64decode(y)
        return int.from_bytes(t, 'big')
    s = s.split('-')
    s = tuple([tmp(x) for x in s])
    return rsa.PrivateKey(*s)

class AESCipher(object):
    def __init__(self, key):
        self.bs = AES.block_size
        self.key = rsa.compute_hash(key, 'SHA-256')
    def encrypt(self, raw): # str -> str
        raw = self._pad(raw)
        iv = rsa.randnum.read_random_bits(self.bs * 8)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return base64.b64encode(iv + cipher.encrypt(raw.encode())).decode("utf-8")
    def decrypt(self, enc): # str -> str
        enc = base64.b64decode(enc)
        iv = enc[:self.bs]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return self._unpad(cipher.decrypt(enc[self.bs:])).decode("utf-8")
    def _pad(self, s):
        return s + (self.bs - len(s) % self.bs) * chr(self.bs - len(s) % self.bs)
    @staticmethod
    def _unpad(s):
        return s[:-ord(s[len(s)-1:])]

def encrypt_e2e_req(req, recip_pub_key, sndr_priv_key, aes_key_len=128):
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

def verify_e2e_req(req, sndr_pub_key):
    try:
        rsa.verify((req["hdr"] + req["msg"] + req["aes_key"] + req["time"]).encode("utf-8"), base64.b64decode(req["sign"]), sndr_pub_key)
        return True
    except rsa.pkcs1.VerificationError:
        return False

def decrypt_e2e_req(json_string, recip_priv_key, sndr_pub_key):
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

def create_onboarding_req(uname, time, sndr_pub_key, sndr_priv_key):
    hdr = "onboarding"
    
    msg = uname + ' ' + str(time)
    sign = base64.b64encode(rsa.sign((hdr + msg).encode("utf-8"), sndr_priv_key, "SHA-256")).decode("utf-8")

    return json.dumps({ "hdr":hdr, "msg":msg, "sign":sign })

def verify_onboarding_req(json_string, pub_key):
    req = json.loads(json_string)
    
    try:
        rsa.verify((req["hdr"] + req["msg"]).encode("utf-8"), base64.b64decode(req["sign"]), pub_key)
    except rsa.pkcs1.VerificationError:
        print("Signature mismatch")
        return False
    return True

def create_registering_req(uname, time, sndr_pub_key, sndr_priv_key):
    hdr = "registering"

    msg = uname + ' ' + pub_key_to_str(sndr_pub_key) + ' ' + str(time)
    sign = base64.b64encode(rsa.sign((hdr + msg).encode("utf-8"), sndr_priv_key, "SHA-256")).decode("utf-8")

    return json.dumps({ "hdr":hdr, "msg":msg, "sign":sign })

def verify_registering_req(json_string):
    req = json.loads(json_string)
    pub_key = str_to_pub_key(req["msg"].split()[1])

    try:
        rsa.verify((req["hdr"] + req["msg"]).encode("utf-8"), base64.b64decode(req["sign"]), pub_key)
    except rsa.pkcs1.VerificationError:
        print("Signature mismatch")
        return False
    return True
