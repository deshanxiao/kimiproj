FROM ubuntu:24.04

RUN apt-get update && apt-get install -y \
    gnupg lsb-release software-properties-common curl && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y \
      python3.11 python3.11-distutils python3.11-dev python3.11-venv \
      gcc nodejs npm supervisor vim curl && \
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 创建非 root 用户并切换工作目录
RUN useradd -m sandboxuser && \
    mkdir -p /sandbox/files && \
    chown -R sandboxuser:sandboxuser /sandbox

USER sandboxuser
WORKDIR /sandbox

# 安装 Node.js 依赖
COPY sandbox.js .
COPY package.json .
RUN npm install

# 复制应用文件和 supervisor 配置文件
COPY app.py .
COPY gateway.py .
COPY conf/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# 启动 supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]