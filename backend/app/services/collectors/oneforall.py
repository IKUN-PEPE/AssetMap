import asyncio
import csv
import json
import logging
import os
from pathlib import Path
from typing import Any, List, Dict
from .base import BaseCollector

logger = logging.getLogger(__name__)

class OneForAllCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "oneforall"

    async def test_connection(self, config: Dict[str, Any]) -> bool:
        path = config.get("oneforall_path")
        if not path or not os.path.exists(path):
            return False
        return True

    async def run(self, query: str, options: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        ofa_path = config.get("oneforall_path")
        python_path = config.get("python_path", "python")
        
        if not ofa_path or not os.path.exists(ofa_path):
            logger.error(f"OneForAll path not found: {ofa_path}")
            return []

        # OneForAll 命令: python oneforall.py --target example.com run
        cmd = [python_path, ofa_path, "--target", query, "run"]
        
        logger.info(f"Running OneForAll: {' '.join(cmd)}")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"OneForAll failed with code {process.returncode}: {stderr.decode()}")
                return []

            # OneForAll 结果通常保存在 results 目录下，文件名为 target.csv
            # 我们需要定位输出文件。通常在 oneforall/results/target.csv
            ofa_dir = Path(ofa_path).parent
            result_file = ofa_dir / "results" / f"{query}.csv"
            
            if not result_file.exists():
                logger.error(f"OneForAll result file not found: {result_file}")
                return []
            
            results = []
            with open(result_file, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # OneForAll 字段映射
                    # subdomain, port, ip, title, banner
                    raw = {
                        "host": row.get("subdomain"),
                        "ip": row.get("ip"),
                        "port": row.get("port") or "80",
                        "domain": query,
                        "title": row.get("title"),
                        "server": row.get("banner"),
                        "url": f"http://{row.get('subdomain')}"
                    }
                    results.append(self.normalize(raw))
            
            return results

        except Exception as e:
            logger.error(f"OneForAll execution error: {e}")
            return []
