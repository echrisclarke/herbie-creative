"""Human-friendly CLI progress for campaign runs."""
from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, TextIO


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    mins, secs = divmod(seconds, 60)
    if mins < 60:
        return f"{mins}m {secs:02d}s"
    hours, mins = divmod(mins, 60)
    return f"{hours}h {mins:02d}m {secs:02d}s"


def _bar(done: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return "[" + ("-" * width) + "]"
    ratio = min(1.0, max(0.0, done / total))
    filled = int(round(ratio * width))
    if filled >= width:
        return "[" + ("=" * width) + "]"
    if filled <= 0:
        return "[" + (">" + "-" * (width - 1)) + "]"
    return "[" + ("=" * (filled - 1)) + ">" + ("-" * (width - filled)) + "]"


def _label_ratio(raw: str) -> str:
    text = str(raw or "")
    if text.endswith("-tight"):
        return f"{text[: -len('-tight')]} close-up"
    if text.endswith("-zoomed"):
        return f"{text[: -len('-zoomed')]} zoomed"
    return text


_SPIN = ("|", "/", "-", "\\")


@dataclass
class CliProgress:
    """Pretty terminal progress for pipeline on_event callbacks."""

    stream: TextIO = field(default_factory=lambda: sys.stdout)
    total_steps: int = 0
    completed: int = 0
    started_at: float = field(default_factory=time.perf_counter)
    _current: str | None = None
    _step_started: float | None = None
    _quiet_logging: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _heartbeat_stop: threading.Event = field(default_factory=threading.Event)
    _heartbeat: threading.Thread | None = None
    _spin_i: int = 0
    _live_drawn: bool = False
    _waiting_hint: str | None = None
    _wait_label: str | None = None

    def plan(
        self,
        *,
        campaign: str,
        products: list[str],
        outputs: list[str],
        framing: str,
        locales: list[str],
        creatives_only: bool,
        with_motion: bool = False,
        image_quality: str | None = None,
        outputs_by_product: list[list[str]] | None = None,
        finalize_ratios_by_product: list[list[str] | None] | None = None,
        bonus_locale: str | None = None,
        coverage_note: str | None = None,
    ) -> None:
        if outputs_by_product:
            image_steps = 0
            locale_steps = 0
            for idx, product_outputs in enumerate(outputs_by_product):
                ratios = list(product_outputs) or list(outputs) or ["1:1"]
                frame_steps = 2 if framing == "both" else 1
                image_steps += frame_steps + max(0, len(ratios) - 1) + len(ratios)
                if creatives_only:
                    continue
                if finalize_ratios_by_product and idx < len(finalize_ratios_by_product):
                    fin = finalize_ratios_by_product[idx]
                    fin_ratios = ratios if fin is None else [r for r in ratios if r in fin]
                else:
                    fin_ratios = ratios
                locale_steps += len(fin_ratios) * max(1, len(locales))
            if bonus_locale and not creatives_only:
                locale_steps += 1
            motion_steps = 0
            if with_motion:
                motion_steps = sum(len(p) for p in outputs_by_product)
            self.total_steps = max(1, image_steps + locale_steps + motion_steps)
        else:
            product_count = max(1, len(products))
            ratio_count = max(1, len(outputs))
            frame_steps = 2 if framing == "both" else 1
            # First ratio framing + chained remaining ratios + write/finalize per ratio.
            image_steps = product_count * (frame_steps + max(0, ratio_count - 1) + ratio_count)
            locale_steps = (
                0 if creatives_only else product_count * ratio_count * max(1, len(locales))
            )
            motion_steps = product_count * ratio_count if with_motion else 0
            self.total_steps = max(1, image_steps + locale_steps + motion_steps)
        self.completed = 0
        self.started_at = time.perf_counter()

        self._line("")
        self._line("-" * 72)
        self._line(f"  Campaign   {campaign}")
        if outputs_by_product:
            bits = []
            for i, po in enumerate(outputs_by_product, start=1):
                name = products[i - 1] if i - 1 < len(products) else f"product {i}"
                bits.append(f"P{i} {name}: {', '.join(po)}")
            self._line(f"  Matrix     {' | '.join(bits)}")
            if finalize_ratios_by_product:
                fin_bits = []
                for i, fin in enumerate(finalize_ratios_by_product, start=1):
                    if fin is None:
                        fin_bits.append(f"P{i}=all")
                    elif not fin:
                        fin_bits.append(f"P{i}=none")
                    else:
                        fin_bits.append(f"P{i}={','.join(fin)}")
                self._line(f"  Text on    {'; '.join(fin_bits)}")
        else:
            self._line(
                f"  Products   {max(1, len(products))}  |  Ratios {', '.join(outputs) or '-'}  |  "
                f"Framing {framing}"
            )
        if image_quality:
            self._line(f"  Quality    {image_quality}")
        if creatives_only:
            self._line("  Text       creatives only (no message/CTA stamp)")
        else:
            locs = ", ".join(locales) if locales else "en-US"
            extra = f" + one {bonus_locale} demo" if bonus_locale else ""
            self._line(f"  Locales    {locs}{extra}")
        if with_motion:
            self._line("  Motion     enabled")
        if coverage_note:
            self._line(f"  Coverage   {coverage_note}")
        self._line(f"  Plan       about {self.total_steps} pipeline steps")
        self._line("-" * 72)
        self._line("")
        self._flush()

    def note_live_folder(self, folder: str, *, campaign_id: str | None = None) -> None:
        self._line(f"  Folder     {folder}")
        if campaign_id:
            self._line(f"  Campaign   id={campaign_id}")
        self._line("  UI         Library / Gallery refresh as each file lands")
        self._line("")
        self._flush()

    def quiet_app_logs(self) -> None:
        """Keep noisy pipeline INFO logs out of the way of the progress UI."""
        if self._quiet_logging:
            return
        import logging

        logging.getLogger("app").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        self._quiet_logging = True

    def on_event(self, event: str, data: dict[str, Any]) -> None:
        product = str(data.get("product") or "")
        ratio = _label_ratio(str(data.get("ratio") or ""))
        locale = str(data.get("locale") or "")

        if event == "product.started":
            self._finish_current(ok=True)
            name = product or str(data.get("name") or "product")
            idx = data.get("index")
            total = data.get("total")
            prefix = f"{idx}/{total} " if idx and total else ""
            self._line(f"  > Product  {prefix}{name}")
            self._flush()
            return

        if event == "tile.started":
            self._finish_current(ok=True)
            bits = [b for b in (product, ratio) if b]
            label = " / ".join(bits) or "creative"
            if locale and locale not in {"creative", "motion"}:
                self._begin(
                    f"Stamping text  {label}  ({locale})",
                    hint="composer overlay (usually under 1s)",
                    wait_label="stamping text",
                )
            else:
                self._begin(
                    f"OpenAI image   {label}",
                    hint="waiting on image API (often 20-60s)",
                    wait_label="waiting on OpenAI",
                )
            return

        if event == "tile.completed":
            bits = [b for b in (product, ratio) if b]
            if locale and locale not in {"creative", "motion"}:
                bits.append(locale)
            label = " / ".join(bits) or "creative"
            path = str(data.get("path") or data.get("creative_path") or "")
            provider = str(data.get("image_provider") or data.get("text_provider") or "")
            detail = label
            if provider:
                detail = f"{label}  ({provider})"
            self._complete_step(detail)
            if path:
                self._line(f"             -> {path}")
                self._status_line()
            self._flush()
            return

        if event in {"motion.started"}:
            self._finish_current(ok=True)
            bits = [b for b in (product, ratio, locale) if b]
            suffix = f"  {' / '.join(bits)}" if bits else ""
            self._begin(
                f"Animating{suffix}",
                hint="waiting on motion API",
                wait_label="waiting on motion API",
            )
            return

        if event == "tile.skipped_text":
            bits = [b for b in (product, ratio) if b]
            label = " / ".join(bits) or "creative"
            self._line(f"             - keeping {label} as no-text creative (demo)")
            self._flush()
            return

        if event == "localize.started":
            loc = locale or str(data.get("locale") or "")
            self._line(f"             - localizing copy ({loc}) via OpenAI...")
            self._flush()
            return

        if event == "finalize.started":
            self._finish_current(ok=True)
            name = product or "product"
            ratios = data.get("ratios") or []
            ratio_bit = f"  ratios={','.join(str(r) for r in ratios)}" if ratios else ""
            self._line(f"  > Finalize  {name}  (message / CTA / legal){ratio_bit}")
            self._flush()
            return

        if event in {"motion.completed", "motion.skipped"}:
            label = " / ".join(b for b in (product, ratio) if b) or "motion"
            if event == "motion.skipped":
                self._complete_step(f"Motion skipped  {label}")
            else:
                path = str(data.get("motion_path") or data.get("path") or "")
                self._complete_step(f"Motion ready  {label}")
                if path:
                    self._line(f"             -> {path}")
                    self._status_line()
            self._flush()
            return

        if event == "run.completed":
            self._finish_current(ok=True)
            self.completed = max(self.completed, self.total_steps)
            elapsed = _fmt_duration(time.perf_counter() - self.started_at)
            tiles = data.get("tiles")
            campaign_id = data.get("campaign_id")
            self._line("")
            self._line("-" * 72)
            self._line(f"  Done in {elapsed}")
            if campaign_id:
                self._line(f"  Campaign  {campaign_id}")
            if tiles is not None:
                self._line(f"  Outputs   {tiles} tile(s)")
            self._line(f"  Progress  {_bar(self.total_steps, self.total_steps)}  100%")
            self._line("-" * 72)
            self._line("")
            self._flush()

    def fail(self, message: str) -> None:
        self._finish_current(ok=False)
        self._line("")
        self._line(f"  FAILED: {message}")
        self._line("")
        self._flush()

    def _isatty(self) -> bool:
        try:
            return bool(self.stream.isatty())
        except Exception:
            return False

    def _begin(
        self,
        label: str,
        *,
        hint: str | None = None,
        wait_label: str | None = None,
    ) -> None:
        with self._lock:
            self._clear_live_unlocked()
            self._current = label
            self._step_started = time.perf_counter()
            self._waiting_hint = hint
            self._wait_label = wait_label or "working"
            step = min(self.completed + 1, max(self.total_steps, self.completed + 1))
            total = max(self.total_steps, step)
            self._line(f"  [{step:>2}/{total}] {label} ...")
            if hint:
                self._line(f"             {hint}")
            self._status_line()
            self._flush()
        self._start_heartbeat()

    def _complete_step(self, label: str) -> None:
        self._stop_heartbeat()
        with self._lock:
            self._clear_live_unlocked()
            took = ""
            if self._step_started is not None:
                took = f"  ({_fmt_duration(time.perf_counter() - self._step_started)})"
            self.completed = min(self.completed + 1, max(self.total_steps, self.completed + 1))
            step = self.completed
            total = max(self.total_steps, step)
            self._current = None
            self._step_started = None
            self._waiting_hint = None
            self._wait_label = None
            self._line(f"  [{step:>2}/{total}] OK {label}{took}")
            self._status_line()

    def _finish_current(self, *, ok: bool) -> None:
        self._stop_heartbeat()
        with self._lock:
            if not self._current:
                return
            self._clear_live_unlocked()
            took = ""
            if self._step_started is not None:
                took = f"  ({_fmt_duration(time.perf_counter() - self._step_started)})"
            mark = "OK" if ok else ".."
            self.completed = min(self.completed + 1, max(self.total_steps, self.completed + 1))
            step = self.completed
            total = max(self.total_steps, step)
            self._line(f"  [{step:>2}/{total}] {mark} {self._current}{took}")
            self._current = None
            self._step_started = None
            self._waiting_hint = None
            self._wait_label = None
            self._status_line()

    def _start_heartbeat(self) -> None:
        self._stop_heartbeat()
        self._heartbeat_stop = threading.Event()
        thread = threading.Thread(
            target=self._heartbeat_loop,
            name="cli-progress-heartbeat",
            daemon=True,
        )
        self._heartbeat = thread
        thread.start()

    def _stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        thread = self._heartbeat
        self._heartbeat = None
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.2)

    def _heartbeat_loop(self) -> None:
        # First tick after 1.5s so long OpenAI waits feel alive quickly.
        if self._heartbeat_stop.wait(1.5):
            return
        while not self._heartbeat_stop.is_set():
            with self._lock:
                if self._current and self._step_started is not None:
                    self._draw_live_unlocked()
            # Non-TTY terminals (some Windows launchers) need printed lines, not \r.
            wait = 1.0 if self._isatty() else 2.0
            if self._heartbeat_stop.wait(wait):
                return

    def _draw_live_unlocked(self) -> None:
        assert self._step_started is not None
        step_elapsed = _fmt_duration(time.perf_counter() - self._step_started)
        total_elapsed = _fmt_duration(time.perf_counter() - self.started_at)
        spin = _SPIN[self._spin_i % len(_SPIN)]
        self._spin_i += 1
        total = max(self.total_steps, 1)
        done = min(self.completed, total)
        pct = int(round(100 * done / total))
        hint = self._wait_label or "working"
        text = (
            f"             {spin} {hint}"
            f"  |  this step {step_elapsed}"
            f"  |  elapsed {total_elapsed}"
            f"  |  {_bar(done, total)} {pct:>3}%"
        )
        if self._isatty():
            pad = max(0, 78 - len(text))
            try:
                self.stream.write("\r" + text + (" " * pad))
                self.stream.flush()
                self._live_drawn = True
            except Exception:
                self._line(text)
                self._flush()
        else:
            # Always print heartbeats in non-interactive terminals.
            self._line(text)
            self._flush()

    def _clear_live_unlocked(self) -> None:
        if not self._live_drawn:
            return
        if self._isatty():
            try:
                self.stream.write("\r" + (" " * 78) + "\r")
                self.stream.flush()
            except Exception:
                pass
        self._live_drawn = False

    def _status_line(self) -> None:
        total = max(self.total_steps, 1)
        done = min(self.completed, total)
        pct = int(round(100 * done / total))
        elapsed = _fmt_duration(time.perf_counter() - self.started_at)
        eta = ""
        if done > 0 and done < total:
            rate = (time.perf_counter() - self.started_at) / done
            remaining = rate * (total - done)
            eta = f"  |  eta {_fmt_duration(remaining)}"
        self._line(f"             {_bar(done, total)}  {pct:>3}%  |  elapsed {elapsed}{eta}")

    def _line(self, text: str) -> None:
        try:
            self.stream.write(text + "\n")
        except UnicodeEncodeError:
            self.stream.write(text.encode("ascii", "replace").decode("ascii") + "\n")

    def _flush(self) -> None:
        self.stream.flush()
