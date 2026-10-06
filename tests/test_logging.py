"""服务端日志配置和业务失败原因记录测试。"""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server.controller.errors import api_error
from server.logging_config import configure_server_logging, shutdown_server_logging


class ServerLoggingTests(unittest.TestCase):
    def test_business_error_reason_is_written_and_file_is_released(self):
        """业务校验原因应写入日志，关闭后 Windows 能立即删除日志目录。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "Navi" / "navi.db"
            with patch.dict(
                os.environ,
                {"NAVI_DATABASE_PATH": str(database_path)},
                clear=False,
            ):
                log_path = configure_server_logging()
                api_error(
                    400,
                    "INVALID_REQUEST",
                    "模型地址必须是有效的 http 或 https URL",
                    operation="新增模型配置",
                )
                shutdown_server_logging()

                content = log_path.read_text(encoding="utf-8")
                self.assertIn("operation=新增模型配置", content)
                self.assertIn("code=INVALID_REQUEST", content)
                self.assertIn("模型地址必须是有效的 http 或 https URL", content)


if __name__ == "__main__":
    unittest.main()
