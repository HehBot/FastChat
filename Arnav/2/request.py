import rsa
from Crypto.Cipher import AES
import hashlib
import base64

import json

class AESCipher(object):
    def __init__(self, key):
        self.bs = AES.block_size
        self.key = hashlib.sha256(key).digest()
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

def encrypt(req, recip_pub_key, sndr_priv_key, aes_key_len=128):
    msg = req["msg"]
    time = req["time"]

    aes_key = rsa.randnum.read_random_bits(aes_key_len)
    aes = AESCipher(aes_key)

    enc_msg = aes.encrypt(msg)
    enc_aes_key = base64.b64encode(rsa.encrypt(aes_key, recip_pub_key)).decode('utf-8')
    enc_time = aes.encrypt(time)

    comp_msg = req["hdr"] + enc_msg + enc_aes_key + enc_time
    sign = base64.b64encode(rsa.sign(comp_msg.encode('utf-8'), sndr_priv_key, 'SHA-1')).decode('utf-8')

    x =  json.dumps({ "hdr":req["hdr"], "msg":enc_msg, "aes_key":enc_aes_key, "time":enc_time, "sign":sign })
    
    return x

def decrypt(json_string, recip_priv_key, sndr_pub_key):
    req = json.loads(json_string)
    
    try:
        rsa.verify((req["hdr"] + req["msg"] + req["aes_key"] + req["time"]).encode('utf-8'), base64.b64decode(req["sign"]), sndr_pub_key)
    except rsa.pkcs1.VerificationError:
        print("Signature mismatch")
        return

    aes_key = rsa.decrypt(base64.b64decode(req["aes_key"]), recip_priv_key)
    aes = AESCipher(aes_key)

    msg = aes.decrypt(req["msg"])
    time = aes.decrypt(req["time"])

    return { "hdr":req["hdr"], "msg":msg, "time":time }

(A_pub_key, A_priv_key) = rsa.newkeys(512)
(B_pub_key, B_priv_key) = rsa.newkeys(512)

req = { "hdr":"insert header", "msg":"insert message", "time":"109" }

enc_req = encrypt(req, B_pub_key, A_priv_key)

print(req)
print(enc_req)
print(decrypt(enc_req, B_priv_key, A_pub_key))

"""
mangled_enc_req = enc_req[:-5] + 'T' + enc_req[-4:]
print(mangled_enc_req)
print(decrypt(mangled_enc_req, B_priv_key, A_pub_key))
"""
