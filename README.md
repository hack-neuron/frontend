# frontend

Generate JWT RS256 key:

```bash
ssh-keygen -t rsa -b 1024 -m PEM -f jwt.key
# Don't add passphrase
openssl rsa -in jwt.key -pubout -outform PEM -out jwt.key.pub
```