# Alpha 1.2 开发入口

Alpha 1.2 的主开发计划见 [alpha-1.2-plan.md](../alpha-1.2-plan.md)。

## 核心文档

- [主计划：Network Hosting & Multiplayer Readiness](../alpha-1.2-plan.md)
- [局域网联机配置指南](../lan_play_guide.md)
- [云端服务器部署指南](../cloud_deployment_guide.md)

## 任务板

- [M8：多人联机与局域网部署服务](task_m8_network_hosting.md)

## 相关实现入口

- [server.py](file:///d:/鸦木布拉夫小镇/src/api/server.py)：网络监听端口与自适应 IP 探测逻辑。
- [run_server.bat](file:///d:/鸦木布拉夫小镇/run_server.bat)：Windows 平台下的一键启动脚本。
- [Dockerfile](file:///d:/鸦木布拉夫小镇/Dockerfile) & [docker-compose.yml](file:///d:/鸦木布拉夫小镇/docker-compose.yml)：云端与容器化运行配置。
