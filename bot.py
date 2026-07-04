import os
import io
import logging
import math
from PIL import Image, ImageDraw, ImageFilter, ImageOps
import telebot
from telebot import types

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
bot = telebot.TeleBot(BOT_TOKEN)

# Grid layout options
LAYOUTS = {
    "2x1": {"cols": 2, "rows": 1, "label": "2 Photos Side by Side"},
    "1x2": {"cols": 1, "rows": 2, "label": "2 Photos Stacked"},
    "2x2": {"cols": 2, "rows": 2, "label": "4 Photo Grid"},
    "3x1": {"cols": 3, "rows": 1, "label": "3 Photos in a Row"},
    "3x2": {"cols": 3, "rows": 2, "label": "6 Photo Grid"},
    "3x3": {"cols": 3, "rows": 3, "label": "9 Photo Grid"},
}

STYLES = {
    "Clean": {
        "bg": (255, 255, 255),
        "gap": 8,
        "padding": 20,
        "radius": 0,
        "shadow": False,
    },
    "Dark": {
        "bg": (18, 18, 18),
        "gap": 8,
        "padding": 20,
        "radius": 0,
        "shadow": False,
    },
    "Rounded": {
        "bg": (240, 240, 245),
        "gap": 12,
        "padding": 24,
        "radius": 18,
        "shadow": True,
    },
    "Polaroid": {
        "bg": (245, 243, 235),
        "gap": 20,
        "padding": 40,
        "radius": 4,
        "shadow": True,
    },
    "Neon": {
        "bg": (8, 8, 20),
        "gap": 4,
        "padding": 16,
        "radius": 8,
        "shadow": False,
    },
}

CELL_SIZE = 400  # px per cell

user_sessions = {}


def rounded_paste(canvas, img, pos, radius, shadow=False):
    x, y = pos
    w, h = img.size

    if shadow:
        sh = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle(
            [(0, 0), (w + 19, h + 19)], radius=radius + 4, fill=(0, 0, 0, 80)
        )
        sh = sh.filter(ImageFilter.GaussianBlur(8))
        canvas.alpha_composite(sh, dest=(x - 4, y - 4))

    if radius > 0:
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=radius, fill=255)
        img = img.convert("RGBA")
        img.putalpha(mask)
        canvas.alpha_composite(img, dest=(x, y))
    else:
        canvas.paste(img.convert("RGB"), (x, y))


def fit_crop(img, target_w, target_h):
    """Crop image to fill target size while maintaining aspect ratio."""
    img_w, img_h = img.size
    scale = max(target_w / img_w, target_h / img_h)
    new_w = int(img_w * scale)
    new_h = int(img_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def make_collage(images: list, layout_key: str, style_key: str) -> bytes:
    layout = LAYOUTS[layout_key]
    style = STYLES[style_key]

    cols = layout["cols"]
    rows = layout["rows"]
    gap = style["gap"]
    pad = style["padding"]
    radius = style["radius"]
    bg = style["bg"]

    cell_w = CELL_SIZE
    cell_h = CELL_SIZE

    # Special taller cell for portrait-heavy grids
    if rows == 1:
        cell_h = int(CELL_SIZE * 1.2)

    canvas_w = cols * cell_w + (cols - 1) * gap + pad * 2
    canvas_h = rows * cell_h + (rows - 1) * gap + pad * 2

    canvas = Image.new("RGBA", (canvas_w, canvas_h), bg + (255,))

    # Neon grid lines
    if style_key == "Neon":
        draw = ImageDraw.Draw(canvas)
        neon_colors = [(0, 255, 170), (255, 0, 200), (0, 200, 255)]
        for i in range(cols - 1):
            lx = pad + (i + 1) * cell_w + i * gap + gap // 2
            draw.line([(lx, 0), (lx, canvas_h)], fill=neon_colors[i % 3] + (60,), width=2)
        for j in range(rows - 1):
            ly = pad + (j + 1) * cell_h + j * gap + gap // 2
            draw.line([(0, ly), (canvas_w, ly)], fill=neon_colors[j % 3] + (60,), width=2)

    # Polaroid bottom label area
    polaroid_label_h = 40 if style_key == "Polaroid" else 0
    if polaroid_label_h:
        cell_h_inner = cell_h - polaroid_label_h
    else:
        cell_h_inner = cell_h

    for idx, img in enumerate(images):
        col = idx % cols
        row = idx // cols
        x = pad + col * (cell_w + gap)
        y = pad + row * (cell_h + gap)

        # Crop to cell
        cropped = fit_crop(img, cell_w, cell_h_inner)

        if style_key == "Polaroid":
            # White polaroid card
            card = Image.new("RGBA", (cell_w, cell_h), (255, 255, 255, 255))
            card.paste(cropped.convert("RGB"), (0, 0))
            # Label area is white already
            rounded_paste(canvas, card, (x, y), radius=radius, shadow=style["shadow"])
        else:
            rounded_paste(canvas, cropped, (x, y), radius=radius, shadow=style["shadow"])

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="JPEG", quality=92, optimize=True)
    out.seek(0)
    return out.read()


# ---- Bot flow ----

def send_layout_picker(cid):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("◼◼ 2 Side by Side", callback_data="layout:2x1"),
        types.InlineKeyboardButton("◼\n◼ 2 Stacked", callback_data="layout:1x2"),
        types.InlineKeyboardButton("◼◼◼ 3 in a Row", callback_data="layout:3x1"),
        types.InlineKeyboardButton("▦ 4 Grid (2×2)", callback_data="layout:2x2"),
        types.InlineKeyboardButton("▦ 6 Grid (3×2)", callback_data="layout:3x2"),
        types.InlineKeyboardButton("▦ 9 Grid (3×3)", callback_data="layout:3x3"),
    )
    bot.send_message(
        cid,
        "🖼 *Step 1 — Choose a layout:*",
        parse_mode="Markdown",
        reply_markup=markup,
    )


def send_style_picker(cid):
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("⬜ Clean", callback_data="style:Clean"),
        types.InlineKeyboardButton("⬛ Dark", callback_data="style:Dark"),
        types.InlineKeyboardButton("🔲 Rounded", callback_data="style:Rounded"),
        types.InlineKeyboardButton("📷 Polaroid", callback_data="style:Polaroid"),
        types.InlineKeyboardButton("⚡ Neon", callback_data="style:Neon"),
    )
    bot.send_message(
        cid,
        "🎨 *Step 2 — Choose a style:*",
        parse_mode="Markdown",
        reply_markup=markup,
    )


@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    cid = message.chat.id
    bot.send_message(
        cid,
        "👋 *Photo Collage Grid Bot*\n\n"
        "I'll combine your photos into a beautiful grid collage!\n\n"
        "Send /make to start.",
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["make"])
def cmd_make(message):
    cid = message.chat.id
    user_sessions[cid] = {"photos": [], "step": "layout"}
    send_layout_picker(cid)


@bot.callback_query_handler(func=lambda call: call.data.startswith("layout:"))
def handle_layout(call):
    cid = call.message.chat.id
    layout = call.data.split(":")[1]
    session = user_sessions.setdefault(cid, {"photos": []})
    session["layout"] = layout
    session["step"] = "style"

    needed = LAYOUTS[layout]["cols"] * LAYOUTS[layout]["rows"]
    bot.answer_callback_query(call.id, f"Layout selected!")
    bot.edit_message_text(
        f"✅ Layout: *{LAYOUTS[layout]['label']}* — needs {needed} photos",
        cid,
        call.message.message_id,
        parse_mode="Markdown",
    )
    send_style_picker(cid)


@bot.callback_query_handler(func=lambda call: call.data.startswith("style:"))
def handle_style(call):
    cid = call.message.chat.id
    style = call.data.split(":")[1]
    session = user_sessions.setdefault(cid, {})
    session["style"] = style
    session["step"] = "photos"

    layout = session.get("layout", "2x2")
    needed = LAYOUTS[layout]["cols"] * LAYOUTS[layout]["rows"]

    bot.answer_callback_query(call.id, "Style selected!")
    bot.edit_message_text(
        f"✅ Style: *{style}*",
        cid,
        call.message.message_id,
        parse_mode="Markdown",
    )
    bot.send_message(
        cid,
        f"📸 *Step 3 — Send your {needed} photos!*\n\n"
        f"Send them one by one. I'll tell you how many are left.\n"
        f"_(Send as photos, not files, for best quality)_",
        parse_mode="Markdown",
    )


@bot.message_handler(
    content_types=["photo", "document"],
    func=lambda m: user_sessions.get(m.chat.id, {}).get("step") == "photos",
)
def handle_photo(message):
    cid = message.chat.id
    session = user_sessions.get(cid, {})
    layout = session.get("layout", "2x2")
    needed = LAYOUTS[layout]["cols"] * LAYOUTS[layout]["rows"]

    try:
        if message.content_type == "photo":
            file_id = message.photo[-1].file_id
        else:
            if not message.document.mime_type.startswith("image/"):
                bot.send_message(cid, "⚠️ Please send an image.")
                return
            file_id = message.document.file_id

        file_info = bot.get_file(file_id)
        img_bytes = bot.download_file(file_info.file_path)
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        session["photos"].append(img)

        received = len(session["photos"])
        remaining = needed - received

        if remaining > 0:
            bot.send_message(
                cid,
                f"✅ Photo {received}/{needed} received! Send {remaining} more.",
            )
        else:
            session["step"] = "done"
            generating_msg = bot.send_message(cid, "⏳ Building your collage…")
            try:
                result = make_collage(session["photos"][:needed], layout, session.get("style", "Clean"))
                bot.send_photo(
                    cid,
                    result,
                    caption=(
                        "🖼 *Your collage is ready!*\n\n"
                        "Send /make to create another one."
                    ),
                    parse_mode="Markdown",
                )
                bot.delete_message(cid, generating_msg.message_id)
            except Exception as e:
                logger.exception("Collage error")
                bot.send_message(cid, f"❌ Failed to generate collage: {e}")

    except Exception as e:
        logger.exception("Photo handling error")
        bot.send_message(cid, f"❌ Error processing photo: {e}")


@bot.message_handler(commands=["cancel"])
def cmd_cancel(message):
    cid = message.chat.id
    user_sessions.pop(cid, None)
    bot.send_message(cid, "❌ Cancelled. Send /make to start over.")


if __name__ == "__main__":
    logger.info("Collage bot starting…")
    bot.infinity_polling()
