# 脚本用途

以下命令均从项目根目录执行。日常启动使用 `bash scripts/start_all.sh`，
查看状态和停止分别使用 `status`、`stop`，强制重启使用 `restart`。

| 文件 | 用途 |
| --- | --- |
| `start_all.sh` | 检查依赖并启动后端、前端、RQ Worker、调度器和 WebBridge；代码变化时刷新应用进程 |
| `start_rq_worker.sh` | 单独启动采集、Agent、训练和报告任务 Worker；也被一键启动脚本调用 |
| `start_monitoring_scheduler.sh` | 单独启动自动采集与报告调度器；也被一键启动脚本调用 |
| `start_alert_scheduler.sh` | 单独启动告警调度器；也被一键启动脚本调用 |
| `start_web.sh` | 单独启动 FastAPI，托管已经构建的前端；不启动 Vite、Worker 或调度器 |
| `start_webbridge.sh` | 单独启动浏览器采集通道 |
| `up_dev.sh` / `down_dev.sh` | 启停可选的 Docker Compose 开发依赖（PostgreSQL、Redis、Prometheus）；与本机安装方式不同 |
| `apply_migrations.sh` | 新库初始化和版本化迁移，CI 也会调用 |
| `configure_production_auth.py` | 初始化管理员和认证配置 |
| `test_alert_destination.py` | 向指定邮箱或 Webhook 发送真实测试通知 |
| `backup_postgres.sh` | 数据库备份与归档校验；配置 S3 时调用上传脚本 |
| `upload_backup.py` | 上传备份到已配置的对象存储 |
| `verify_postgres_backup.sh` | 检查备份校验和和归档目录；不等同于恢复演练 |
| `install_backup_timer.sh` | 安装当前用户的每日备份 systemd timer |

## 已清理的重复入口

- `generate_category_seed.py`、`seed_categories.sql`：分类种子已完整包含在
  `brandpulse-infra/init-scripts/01_create_tables.sql` 中，由初始化流程加载。
  后续分类变更应通过新增版本化迁移维护，已有数据库无需重新执行基础建表脚本。
- `run_aggregate.sh`：指标流水线已自动同步兼容时序表，删除重复 Shell 包装。
  如需单独修复历史兼容指标，仍可使用原模块入口：

  ```bash
  PYTHONPATH=src/backend:src .venv/bin/python -m brandpulse.indicators.jobs.aggregate --date 2026-08-29
  ```

清理只删除仓库文件，不删除数据库分类或历史指标。被删除文件可从 Git 历史恢复。
