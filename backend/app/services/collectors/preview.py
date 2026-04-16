import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def get_csv_preview(file_path: Path) -> dict:
    """
    读取 CSV 的前 10 行并返回预览数据。
    """
    headers = []
    rows = []
    
    if not file_path.exists():
        logger.error("File not found for preview: %s", file_path)
        return {"headers": [], "rows": []}

    try:
        # 推荐使用 utf-8-sig 以兼容 Excel 导出的带有 BOM 的 CSV
        with open(file_path, mode='r', encoding='utf-8-sig', errors='replace') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames if reader.fieldnames else []
            
            count = 0
            for row in reader:
                if count >= 10:
                    break
                # 将 dict 中的 None 转换为字符串 "None" 或空字符串
                rows.append({k: (v if v is not None else "") for k, v in row.items()})
                count += 1
                
        logger.info("Generated CSV preview for %s, rows=%s", file_path.name, len(rows))
    except Exception as e:
        logger.exception("Failed to get CSV preview for %s: %s", file_path, e)
        # 如果 utf-8-sig 失败，可以考虑尝试其他编码，但这里先按要求实现
        raise e
    
    return {"headers": headers, "rows": rows}
