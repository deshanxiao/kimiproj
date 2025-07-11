# 使⽤ Docker 搭建⼀个 Sandbox 镜像，对外提供⽂件管理、进程管理、代码执⾏等功能

## API

### /{sessionid}/processes

使用 psutil 包列出所有的进程

### /{sessionid}/process/kill/{pid}

给定进程ID，终止对应的进程

### /{sessionid}/files/upload

给定文件名和文件对象，上传文件，若文件存在，抛出异常。文件大小不能超过一定的阈值 （10MB）

### /{sessionid}/files/delete/{filename}

给定文件名，删除对应文件

### /{sessionid}/files/download/{filename}

下载文件内容

### /{sessionid}/files/list

列出上传的所有文件

### /{sessionid}/files/list

列出上传的所有文件

### /{sessionid}/exec/python

执行python对应的代码

### /{sessionid}/exec/nodejs

执行nodejs代码

### GET /{sessionid}/result

获取执行结果

## 执行Python代码

为了避免stdin阻塞代码，我们可以

- 设置超时时间，最多允许python代码执行10s
- 将stderr设置为/dev/null或直接关闭它。
- 将某个文件，或者页面的临时输入作为stdin。

为了得到exec最后一行的结果 （比如用户执行了 1+1），我们使用ast.parse解析要执行的代码，并且报错最后表达式的结果到result。对于stderr,stdout，我们
在执行代码的过程中将stderr,stdout重定向到stderr,stdout的StringIO对象，并返回给用户。

为了截获图形对象，我们需要重写
plt.Figure = CustomFigure

``` python
# 存储所有 Base64 图像
captured_images = []

# 自定义 Figure 类
class CustomFigure(Figure):
    def show(self):
        # 重写 show 方法，捕获图像
        buf = io.BytesIO()
        self.savefig(buf, format='png')
        buf.seek(0)
        image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        captured_images.append(image_base64)
        super().show()

# 设置 Matplotlib 使用自定义 Figure
plt.Figure = CustomFigure
```

并将它作为pre-run code在用户代码前执行。

总的流程大致是这样的。
1. 用户发送python代码
2. 接收python代码，运行pre-run code,重定向stdin
3. 执行用户代码
4. 用户调用GET /{sessionid}/result获取结果，如果执行完成，返回结果，否则返回Running。

GET /{sessionid}/result 应该可以返回当前已生成的stderr,stdout支持page和oartial output.

## 执行NodeJs代码

使用vm2模块保证安全隔离的执行环境。将用户代码拼接到预先准备好的sandbox.js到临时目录，并执行nodejs代码。

## 安全容器
安全容器通过强化容器与宿主系统的隔离，防止容器内进程对宿主系统、其他容器或网络造成威胁。主要方案包括使用 gVisor（用户空间内核）、Kata Containers（轻量虚拟机）、Firecracker（微虚拟机）、seccomp（系统调用过滤）等技术。这些方案通过虚拟化、限制系统调用、强化权限管理等手段，提供比传统容器更强的安全性。
通过指定下面的命令来在docker中启动gVisor

```
--runtime=runsc
```

# 搭建⼀个⽀持混合云的 Sandbox 调度系统。

## 需求分析

我们本地部署了一个一定规模的K8S集群，在资源充足时，使用本地的K8S集群进行代码执行。在资源不充足时，使用云厂商的K8S集群进行动态扩容。

## 总体架构

<img width="1212" height="605" alt="image" src="https://github.com/user-attachments/assets/da5c34ec-633b-4e6b-9d15-596f93c9d7dc" />

### 本地执行

本地K8S和远端K8S集群会暴露一个Ingress服务 Gataway API 用于决策路由。它可以部署多个实例，通过配置NGINX的转发规则可以保证同一个sessionid一定由一个
Gateway实例处理。

在本地Gateway收到请求后，它会根据metrics server的情况判断本地K8S集群的水位情况，如果水位足够，它将动态创建一个sandbox pod以sessionid命名。

用户通过轮训POD的状态，来开始决定提交代码。当POD ready后，Gateway将提交代码执行。

这时，用户会使用 GET /result API不断轮询结果，当代码执行完成或者超时后，Gateway将负责清理POD资源。

### 远端执行

当本地水位不够时，该请求将转发到云端K8S的Gateway。后面的步骤应该是一样的。这里本地Gateway需要记录哪些sessionId走了远端执行，后面遇到远端执行的实例直接转发即可。













