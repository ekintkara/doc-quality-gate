import os, sys
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import litellm.proxy.common_utils.banner as banner_module
banner_module.show_banner = lambda: None

from litellm import run_server
run_server(["--config", "config/litellm/config.yaml", "--port", "4000"])
