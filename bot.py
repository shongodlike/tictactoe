#!/usr/bin/env python3

import logging
import random
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, InlineQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

TIMER_SECONDS = 15

class Game:
    def __init__(self, mode):
        self.board = [' '] * 9
        self.player = '❌'
        self.winner = None
        self.over = False
        self.mode = mode
        self.p1 = None
        self.p2 = None
        self.started = (mode == 'bot')
        self.timer_task = None
    
    def move(self, pos):
        if self.over or self.board[pos] != ' ':
            return False
        self.board[pos] = self.player
        wins = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
        for w in wins:
            if self.board[w[0]] == self.board[w[1]] == self.board[w[2]] != ' ':
                self.winner = self.board[w[0]]
                self.over = True
                return True
        if ' ' not in self.board:
            self.over = True
            return True
        self.player = '⭕' if self.player == '❌' else '❌'
        return True

games = {}

def color_symbol(s):
    if s == '❌':
        return '❌'
    elif s == '⭕':
        return '⭕'
    return '⬜'

def make_board(game):
    keyboard = []
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            cell = i + j
            sym = game.board[cell]
            display = color_symbol(sym) if sym != ' ' else '⬜'
            row.append(InlineKeyboardButton(display, callback_data=f"m{cell}"))
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def get_title(g):
    if g.mode == 'friend':
        return f"❌ @{g.p1} vs ⭕ @{g.p2}"
    return f"❌ @{g.p1} vs 🤖 Bot"

def get_turn_name(g):
    if g.player == '❌':
        return f"@{g.p1}"
    return f"@{g.p2}" if g.mode == 'friend' else '🤖 Bot'

def get_winner_name(g):
    if g.winner == '❌':
        return f"@{g.p1}"
    return f"@{g.p2}" if g.mode == 'friend' else '🤖 Bot'

def cancel_timer(g):
    if g and g.timer_task and not g.timer_task.done():
        g.timer_task.cancel()
        g.timer_task = None

async def run_timer(app, mid, game):
    try:
        # Обновляем таймер только в ключевые моменты: 10, 5, 3, 2, 1
        updates = [(TIMER_SECONDS - 10, 10), (5, 5), (2, 3), (1, 2), (1, 1), (1, 0)]
        for sleep_time, remaining in updates:
            await asyncio.sleep(sleep_time)
            if game.over or games.get(mid) is not game:
                return
            if remaining > 0:
                text = f"{get_title(game)}\n\nХод: {get_turn_name(game)} ⏱ {remaining}с"
                try:
                    await app.bot.edit_message_text(text=text, inline_message_id=mid, reply_markup=make_board(game))
                except Exception:
                    pass

        # Время вышло
        if game.over or games.get(mid) is not game:
            return

        skipped_name = get_turn_name(game)

        if game.mode == 'friend':
            # Передаём ход другому игроку
            game.player = '⭕' if game.player == '❌' else '❌'
            next_name = get_turn_name(game)
            text = f"{get_title(game)}\n\n⏰ {skipped_name} не успел! Ход: {next_name} ⏱ {TIMER_SECONDS}с"
            try:
                await app.bot.edit_message_text(text=text, inline_message_id=mid, reply_markup=make_board(game))
            except Exception:
                pass
            game.timer_task = asyncio.create_task(run_timer(app, mid, game))
        else:
            # Бот ходит за игрока
            empty = [i for i in range(9) if game.board[i] == ' ']
            if empty:
                game.move(random.choice(empty))
            title = get_title(game)
            if game.over:
                result = f"\n\n🏆 {get_winner_name(game)} выиграл!" if game.winner else "\n\n🤝 Ничья!"
                text = title + result
                try:
                    await app.bot.edit_message_text(text=text, inline_message_id=mid, reply_markup=make_board(game))
                except Exception:
                    pass
            else:
                text = f"{title}\n\nХод: @{game.p1} ⏱ {TIMER_SECONDS}с"
                try:
                    await app.bot.edit_message_text(text=text, inline_message_id=mid, reply_markup=make_board(game))
                except Exception:
                    pass
                game.timer_task = asyncio.create_task(run_timer(app, mid, game))
    except asyncio.CancelledError:
        pass

async def inline_q(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    r = [InlineQueryResultArticle(
        id="1",
        title="Крестики-нолики",
        input_message_content=InputTextMessageContent("Выбери режим:"),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 Бот", callback_data="bot"), InlineKeyboardButton("👥 Друг", callback_data="friend")]
        ])
    )]
    await update.inline_query.answer(r)

async def btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    mid = q.inline_message_id
    user = q.from_user.username or str(q.from_user.id)

    if mid not in games:
        games[mid] = None

    # Новая игра с ботом
    if q.data == "bot":
        cancel_timer(games.get(mid))
        g = Game('bot')
        g.p1 = user
        g.p2 = 'Bot'
        g.started = True
        games[mid] = g
        text = f"{get_title(g)}\n\nХод: @{user} ⏱ {TIMER_SECONDS}с"
        await q.edit_message_text(text, reply_markup=make_board(g))
        g.timer_task = asyncio.create_task(run_timer(ctx.application, mid, g))
        return

    # Новая игра с другом
    if q.data == "friend":
        cancel_timer(games.get(mid))
        g = Game('friend')
        g.p1 = user
        games[mid] = g
        text = f"❌ @{user}\n⭕ ждёт игрока..."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Присоединиться", callback_data="join")]])
        await q.edit_message_text(text, reply_markup=kb)
        return

    # Присоединиться
    if q.data == "join":
        g = games[mid]
        if not g:
            await q.edit_message_text("Игра устарела, создай новую")
            return
        if g.p2:
            await q.answer("Игра уже заполнена!", show_alert=True)
            return
        if g.p1 == user:
            await q.answer("Ты создатель игры!", show_alert=True)
            return
        g.p2 = user
        g.started = True
        text = f"{get_title(g)}\n\nХод: @{g.p1} ⏱ {TIMER_SECONDS}с"
        await q.edit_message_text(text, reply_markup=make_board(g))
        g.timer_task = asyncio.create_task(run_timer(ctx.application, mid, g))
        return

    # Ход
    if q.data.startswith("m"):
        g = games[mid]
        if not g or not g.started:
            await q.answer("Игра не начата", show_alert=True)
            return

        pos = int(q.data[1])

        if g.mode == 'friend':
            expected = g.p1 if g.player == '❌' else g.p2
            if expected != user:
                await q.answer(f"Сейчас ход @{expected}!", show_alert=True)
                return
        elif g.mode == 'bot':
            if g.player == '❌' and g.p1 != user:
                await q.answer(f"Это игра @{g.p1}!", show_alert=True)
                return

        cancel_timer(g)
        g.move(pos)

        # Ход бота
        if g.mode == 'bot' and not g.over and g.player == '⭕':
            empty = [i for i in range(9) if g.board[i] == ' ']
            if empty:
                g.move(random.choice(empty))

        title = get_title(g)
        if g.over:
            result = f"\n\n🏆 {get_winner_name(g)} выиграл!" if g.winner else "\n\n🤝 Ничья!"
            text = title + result
        else:
            text = f"{title}\n\nХод: {get_turn_name(g)} ⏱ {TIMER_SECONDS}с"

        await q.edit_message_text(text, reply_markup=make_board(g))

        if not g.over:
            g.timer_task = asyncio.create_task(run_timer(ctx.application, mid, g))

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎮 Используй @tictacinlinebot в любом чате!")

app = Application.builder().token("8641986898:AAHBjwSF3TDgLTpAzfIHIrnTdvb3hx3ivy4").build()
app.add_handler(CommandHandler("start", start))
app.add_handler(InlineQueryHandler(inline_q))
app.add_handler(CallbackQueryHandler(btn))
print("✅ Бот запущен")
app.run_polling()
