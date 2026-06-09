# 《鸦木布拉夫小镇》云端服务器部署指南

本指南将指导您如何将游戏引擎部署到云端服务器，以便其他玩家只需通过一个公开的网页链接（HTTP）即可访问并游玩。

由于我们已经在 Alpha 1.2 中为项目配置了标准的 **`Dockerfile`** 与 **`docker-compose.yml`**，且支持动态解析环境变量端口，您可以选择以下两种主流云部署方案：

---

## 方案一：部署到容器托管平台（推荐：极速且免运维）

容器托管平台（如 **Railway.app**、**Render.com**、**Zeabur** 等）支持直接导入您的 GitHub 仓库并一键构建上线，非常适合非运维技术人员。

### 部署步骤（以 Railway 为例）：
1. 将您的代码推送到您的个人 **GitHub 仓库**。
2. 登录 **[Railway.app](https://railway.app/)**（可以使用 GitHub 账号直接关联）。
3. 点击 **New Project** -> **Deploy from GitHub repo**，选择您的《鸦木布拉夫小镇》项目仓库。
4. **配置环境变量 (Variables)**：
   在 Railway 的项目设置中，添加以下环境变量：
   - `BOTC_BACKEND` = `live` （或者 `mock`，若使用 mock 模式）
   - `OPENAI_API_KEY` = `你的模型API密钥`
   - `OPENAI_BASE_URL` = `你的模型API网关（如 https://api.siliconflow.cn/v1 或 https://api.openai.com/v1）`
   - `PORT` = `8000` （Railway 会自动将其映射为公网 80 端口）
5. **构建并上线**：
   Railway 会自动检测到根目录的 `Dockerfile` 并开始自动构建。构建完成后，系统会生成一个专属的公网链接（如 `https://ravenswood-bluff-production.up.railway.app`）。
6. 将该链接发给朋友，大家直接在浏览器中打开即可开始游戏！

---

## 方案二：部署到传统云服务器 (如 腾讯云/阿里云/华为云 VPS)

如果您租用了标准的 Linux 云服务器（如 Ubuntu 20.04/22.04），可以使用 Docker Compose 进行部署。

### 前置条件：
确保服务器已安装 **Git**、**Docker** 和 **Docker Compose**：
```bash
# Ubuntu/Debian 安装命令参考
sudo apt update
sudo apt install -y git docker.io docker-compose
```

### 部署步骤：
1. **拉取代码**：
   ```bash
   git clone <你的项目Git仓库地址> /opt/ravenswood-bluff
   cd /opt/ravenswood-bluff
   ```
2. **配置环境变量**：
   在项目根目录下创建 `.env` 文件：
   ```bash
   nano .env
   ```
   写入以下配置：
   ```env
   # API Keys 配置
   OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxx
   OPENAI_BASE_URL=https://api.openai.com/v1
   
   # 运行参数
   BOTC_BACKEND=live
   BOTC_HOST=0.0.0.0
   BOTC_PORT=8000
   ```
3. **后台运行 Docker 容器**：
   ```bash
   # 使用 docker-compose 后台构建并启动服务
   sudo docker-compose up -d --build
   ```
4. **开放云安全组端口**：
   登录您的云服务器后台（如腾讯云控制台），在**防火墙/安全组**中，添加一条入站规则：
   - 协议：`TCP`
   - 端口：`8000`
   - 策略：`允许`
5. 打开浏览器，输入 `http://<您的云服务器公网IP>:8000` 即可开始联机。

---

## 云端公网运行的注意事项（重要）

1. **单房间模式**：目前部署至云端的版本属于**单大厅对局系统**。如果有几批不同的测试组在同一时间进入，他们会进入同一个游戏大厅并相互干扰。建议在私密、约定的内测范围中使用此云端链接。
2. **API 额度安全**：云端部署使用的是您在后台配置的大模型 API 密钥。为防止公开链接被路人刷爆 Token 额度，请**不要将部署链接公开在公共社交媒体上**，仅在内测小群中分享。
