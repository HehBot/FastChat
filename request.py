import rsa
from Crypto.Cipher import AES
import base64

import json

def pubkey_to_id(pub_key):
    def tmp(x):
        return base64.b64encode(x.to_bytes((x.bit_length() + 7) // 8, byteorder='big')).decode('utf-8')
    return tmp(getattr(pub_key, "n")) + '-' + tmp(getattr(pub_key, "e"))

def id_to_pubkey(sid):
    def tmp(y):
        t = base64.b64decode(y)
        return int.from_bytes(t, 'big')
    s = sid.split('-')
    return rsa.PublicKey(tmp(s[0]), tmp(s[1]))

class AESCipher(object):
    def __init__(self, key):
        self.bs = AES.block_size
        self.key = rsa.compute_hash(key, 'SHA-256')
    def encrypt(self, raw): # returns string
        raw = self._pad(raw)
        iv = rsa.randnum.read_random_bits(self.bs * 8)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return base64.b64encode(iv + cipher.encrypt(raw.encode())).decode('utf-8')
    def decrypt(self, enc):
        enc = base64.b64decode(enc)
        iv = enc[:self.bs]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return self._unpad(cipher.decrypt(enc[self.bs:])).decode('utf-8')
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
    enc_aes_key = base64.b64encode(rsa.encrypt(aes_key, recip_pub_key)).decode('utf-8')
    enc_time = aes.encrypt(time)

    comp_msg = req["hdr"] + enc_msg + enc_aes_key + enc_time
    sign = base64.b64encode(rsa.sign(comp_msg.encode('utf-8'), sndr_priv_key, 'SHA-1')).decode('utf-8')

    return json.dumps({ "hdr":req["hdr"], "msg":enc_msg, "aes_key":enc_aes_key, "time":enc_time, "sign":sign })

def decrypt_e2e_req(json_string, recip_priv_key, sndr_pub_key):
    req = json.loads(json_string)
    
    try:
        rsa.verify((req["hdr"] + req["msg"] + req["aes_key"] + req["time"]).encode('utf-8'), base64.b64decode(req["sign"]), sndr_pub_key)
    except rsa.pkcs1.VerificationError:
        print("Signature mismatch")
        # TODO
        return

    aes_key = rsa.decrypt(base64.b64decode(req["aes_key"]), recip_priv_key)
    aes = AESCipher(aes_key)

    msg = aes.decrypt(req["msg"])
    time = aes.decrypt(req["time"])

    return { "hdr":req["hdr"], "msg":msg, "time":time }

def create_onboarding_req(sndr_pub_key, sndr_priv_key):
    hdr = "onboarding"
    
    msg = pubkey_to_id(sndr_pub_key)
    sign = base64.b64encode(rsa.sign(msg.encode('utf-8'), sndr_priv_key, 'SHA-1')).decode('utf-8')

    return json.dumps({ "hdr":hdr, "msg":msg, "sign":sign })

def verify_onboarding_req(json_string):
    req = json.loads(json_string)
    pub_key = id_to_pubkey(req["msg"])
    
    try:
        rsa.verify(req["msg"].encode('utf-8'), base64.b64decode(req["sign"]), pub_key)
    except rsa.pkcs1.VerificationError:
        print("Signature mismatch")
        return False
    return True
