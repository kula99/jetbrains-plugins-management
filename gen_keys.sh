echo ${1}

echo "-------------------------"
key_dir=keys/${1}
mkdir -p ${key_dir}

key_len=2048
if [ $# -eq 2 ]; then
  key_len=${2}
fi

echo "key_len is set to ${key_len}"

# 生成私钥
openssl genrsa -out ${key_dir}/${1}_key_rsa.pem ${key_len}
# 私钥转成pkcs8格式
openssl pkcs8 -in ${key_dir}/${1}_key_rsa.pem -out ${key_dir}/${1}_priv_pkcs8.pem -nocrypt -topk8
# 提取公钥
openssl rsa -in ${key_dir}/${1}_key_rsa.pem -out ${key_dir}/${1}_pub_rsa.pem - RSAPublicKey_out
# 公钥转成pkcs8格式
openssl rsa -in ${key_dir}/${1}_key_rsa.pem -out ${key_dir}/${1}_pub_pkcs8.pem -pubout

# 私钥pkcs8格式转换回pkcs1格式
#openssl rsa -in ${key_dir}/${1}_priv_pkcs8.pem -out ${key_dir}/${1}_key_pkcs1.pem

# 公钥pkcs8格式转换回pkcs1格式
#openssl rsa -pubin -in ${key_dir}/${1}_pub_pkcs8.pem -RSAPublicKey_out -out ${key_dir}/${1}_pub_pkcs1.pem