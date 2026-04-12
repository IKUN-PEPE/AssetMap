import logging
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asset_mapping_screenshot_xlsx.web_screenshot_xlsx import build_run_config, run_job


def open_path(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])


class GuiLogBuffer:
    def __init__(self) -> None:
        self._messages: list[str] = []
        self._lock = threading.Lock()

    def append(self, level: str, message: str) -> None:
        with self._lock:
            self._messages.append(f"[{level}] {message}")

    def drain(self) -> list[str]:
        with self._lock:
            messages = list(self._messages)
            self._messages.clear()
        return messages


class QueueLogHandler(logging.Handler):
    def __init__(self, buffer: GuiLogBuffer) -> None:
        super().__init__()
        self.buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        self.buffer.append(record.levelname, self.format(record))


def build_default_form_values() -> dict[str, str]:
    return {
        "input_path": "",
        "max_items": "0",
        "concurrency": "5",
        "retry_count": "1",
        "timeout_sec": "15",
        "wait_after_load": "5",
    }


def coerce_form_values(
    input_path: str,
    max_items: str,
    concurrency: str,
    retry_count: str,
    timeout_sec: str,
    wait_after_load: str,
    skip_existing: bool,
    headful: bool,
    base_dir: Path,
) -> dict[str, object]:
    return build_run_config(
        input_path=Path(input_path),
        base_dir=base_dir,
        max_items=int(max_items),
        concurrency=int(concurrency),
        retry_count=int(retry_count),
        timeout_sec=int(timeout_sec),
        wait_after_load=int(wait_after_load),
        skip_existing=skip_existing,
        headful=headful,
    )


class ScreenshotGuiApp:
    def __init__(self) -> None:
        self.base_dir = Path(__file__).resolve().parent
        self.log_buffer = GuiLogBuffer()
        self.worker_thread: threading.Thread | None = None
        self.root = tk.Tk()
        self.root.title("Asset Mapping Screenshot XLSX")
        self.root.geometry("920x700")

        defaults = build_default_form_values()
        self.input_var = tk.StringVar(value=defaults["input_path"])
        self.max_items_var = tk.StringVar(value=defaults["max_items"])
        self.concurrency_var = tk.StringVar(value=defaults["concurrency"])
        self.retry_count_var = tk.StringVar(value=defaults["retry_count"])
        self.timeout_sec_var = tk.StringVar(value=defaults["timeout_sec"])
        self.wait_after_load_var = tk.StringVar(value=defaults["wait_after_load"])
        self.skip_existing_var = tk.BooleanVar(value=True)
        self.headful_var = tk.BooleanVar(value=False)

        self._build_layout()
        self.root.after(200, self._poll_logs)

    def _build_layout(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        form = ttk.Frame(main)
        form.pack(fill=tk.X)

        ttk.Label(form, text="Excel 文件").grid(row=0, column=0, sticky=tk.W, pady=4)
        ttk.Entry(form, textvariable=self.input_var, width=70).grid(row=0, column=1, sticky=tk.EW, pady=4)
        ttk.Button(form, text="选择文件", command=self.choose_file).grid(row=0, column=2, padx=8)

        fields = [
            ("max_items", self.max_items_var),
            ("concurrency", self.concurrency_var),
            ("retry_count", self.retry_count_var),
            ("timeout_sec", self.timeout_sec_var),
            ("wait_after_load", self.wait_after_load_var),
        ]
        for idx, (label, var) in enumerate(fields, start=1):
            ttk.Label(form, text=label).grid(row=idx, column=0, sticky=tk.W, pady=4)
            ttk.Entry(form, textvariable=var, width=20).grid(row=idx, column=1, sticky=tk.W, pady=4)

        ttk.Checkbutton(form, text="skip_existing", variable=self.skip_existing_var).grid(row=6, column=0, sticky=tk.W, pady=4)
        ttk.Checkbutton(form, text="headful", variable=self.headful_var).grid(row=6, column=1, sticky=tk.W, pady=4)

        button_bar = ttk.Frame(main)
        button_bar.pack(fill=tk.X, pady=10)
        self.start_button = ttk.Button(button_bar, text="开始截图", command=self.start_job)
        self.start_button.pack(side=tk.LEFT)
        ttk.Button(button_bar, text="打开截图目录", command=self.open_screenshots_dir).pack(side=tk.LEFT, padx=8)
        ttk.Button(button_bar, text="打开结果目录", command=self.open_results_dir).pack(side=tk.LEFT)

        self.log_output = scrolledtext.ScrolledText(main, height=28, wrap=tk.WORD)
        self.log_output.pack(fill=tk.BOTH, expand=True)

        form.columnconfigure(1, weight=1)

    def choose_file(self) -> None:
        file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
        if file_path:
            self.input_var.set(file_path)

    def append_log(self, message: str) -> None:
        self.log_output.insert(tk.END, message + "\n")
        self.log_output.see(tk.END)

    def _poll_logs(self) -> None:
        for message in self.log_buffer.drain():
            self.append_log(message)
        self.root.after(200, self._poll_logs)

    def _build_logger(self) -> logging.Logger:
        logger = logging.getLogger("asset_mapping_screenshot_xlsx.gui")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        queue_handler = QueueLogHandler(self.log_buffer)
        queue_handler.setFormatter(logging.Formatter("%(message)s"))
        file_handler = logging.FileHandler(self.base_dir / "run.log", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(queue_handler)
        logger.addHandler(file_handler)
        logger.propagate = False
        return logger

    def start_job(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return
        if not self.input_var.get().strip():
            messagebox.showerror("错误", "请先选择 Excel 文件")
            return
        try:
            config = coerce_form_values(
                input_path=self.input_var.get().strip(),
                max_items=self.max_items_var.get().strip(),
                concurrency=self.concurrency_var.get().strip(),
                retry_count=self.retry_count_var.get().strip(),
                timeout_sec=self.timeout_sec_var.get().strip(),
                wait_after_load=self.wait_after_load_var.get().strip(),
                skip_existing=self.skip_existing_var.get(),
                headful=self.headful_var.get(),
                base_dir=self.base_dir,
            )
        except Exception as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        logger = self._build_logger()
        self.start_button.config(state=tk.DISABLED)
        self.append_log("[INFO] 开始执行截图任务")

        def worker() -> None:
            try:
                result = run_job(config, logger=logger)
                self.log_buffer.append("INFO", f"任务完成: {result['result_csv']}")
            except Exception as exc:
                self.log_buffer.append("ERROR", str(exc))
            finally:
                self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def open_screenshots_dir(self) -> None:
        open_path(self.base_dir / "screenshots")

    def open_results_dir(self) -> None:
        open_path(self.base_dir / "results")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    ScreenshotGuiApp().run()


if __name__ == "__main__":
    main()
