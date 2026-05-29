"""
ui_media.py - Utilities for rendering section screens with optional local images.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

_ROOT = Path(__file__).resolve().parent
_IMG_DIR = _ROOT / "img"

SECTION_IMAGE_MAP = {
    "pod": "pod.png",
    "profile": "profile.png",
    "bank": "bank.png",
    "nbr": "bnr.png",
    "bnr": "bnr.png",
    "org": "org.png",
    "pismo": "pismo.png",
    "biz": "biz.png",
    "private": "private.png",
    "credit": "credit.png",
    "cazino": "cazino.png",
    "nalog": "nalog.png",
    "birja": "birja.png",
}

# Дополнительные «мемные» или внешние изображения для разделов, где нет локальных PNG.
# Используем простые публичные заглушки/кошек (Cataas / Picsum) для визуального разнообразия.
SECTION_IMAGE_MAP.update({
    "charity": "https://cataas.com/cat/says/Thanks",
    "media_news": "https://picsum.photos/seed/media_news/800/400",
    "news": "https://picsum.photos/seed/news/800/400",
})


def _resolve_section_image(section_key: Optional[str]) -> Optional[Path | str]:
    key = str(section_key or "").strip().lower()
    filename = SECTION_IMAGE_MAP.get(key)
    if not filename:
        return None
    # Если значение похоже на URL — возвращаем строку URL
    if isinstance(filename, str) and (filename.startswith("http://") or filename.startswith("https://")):
        return filename
    path = _IMG_DIR / str(filename)
    return path if path.exists() and path.is_file() else None


def ensure_back_button(
    reply_markup: Optional[InlineKeyboardMarkup],
    *,
    text: str = "В меню",
    callback_data: str = "back_to_main",
) -> InlineKeyboardMarkup:
    rows = [list(row) for row in (reply_markup.inline_keyboard if reply_markup else [])]
    for row in rows:
        for button in row:
            if str(button.callback_data or "") == callback_data:
                return InlineKeyboardMarkup(inline_keyboard=rows)
    rows.append([InlineKeyboardButton(text=text, callback_data=callback_data)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_section_screen(
    event: Message | CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    parse_mode: Optional[str] = None,
    section_key: Optional[str] = None,
    flag_file_id: Optional[str] = None,
    add_back_to_menu: bool = False,
) -> None:
    """
    Render a section screen with text and an optional image.

    - If img/<section>.png exists, sends or edits photo+caption.
    - If flag_file_id is provided, uses that as the photo source.
    - For callback events, tries to edit current message first.
    """
    markup = ensure_back_button(reply_markup, text="В меню", callback_data="back_to_main") if add_back_to_menu else reply_markup

    media_path = _resolve_section_image(section_key)
    media_file_id = str(flag_file_id or "").strip()
    has_media = bool(media_file_id or media_path)

    def _media_obj():
        if media_file_id:
            return media_file_id
        if media_path:
            # media_path may be a local Path or an external URL string
            if isinstance(media_path, str) and (media_path.startswith("http://") or media_path.startswith("https://")):
                return media_path
            return FSInputFile(str(media_path))
        return None

    async def _safe_edit_text(message: Message) -> bool:
        try:
            if message.photo:
                await message.edit_caption(caption=text, reply_markup=markup, parse_mode=parse_mode)
            else:
                await message.edit_text(text, reply_markup=markup, parse_mode=parse_mode)
            return True
        except TelegramBadRequest as exc:
            low = str(exc).lower()
            if "message is not modified" in low:
                return True
            if "there is no text in the message to edit" in low:
                return False
            return False
        except Exception:
            return False

    if isinstance(event, CallbackQuery):
        message = event.message
        if message is None:
            return

        if has_media:
            media = _media_obj()
            if media is not None:
                try:
                    if message.photo:
                        await message.edit_media(
                            media=InputMediaPhoto(media=media, caption=text, parse_mode=parse_mode),
                            reply_markup=markup,
                        )
                        return
                    await message.answer_photo(
                        media,
                        caption=text,
                        reply_markup=markup,
                        parse_mode=parse_mode,
                    )
                    return
                except TelegramBadRequest as exc:
                    if "message is not modified" in str(exc).lower():
                        return
                except Exception:
                    pass

        if not await _safe_edit_text(message):
            await message.answer(text, reply_markup=markup, parse_mode=parse_mode)
        return

    media = _media_obj()
    if has_media and media is not None:
        try:
            await event.answer_photo(media, caption=text, reply_markup=markup, parse_mode=parse_mode)
            return
        except Exception:
            pass
    await event.answer(text, reply_markup=markup, parse_mode=parse_mode)
