import os
from io import BytesIO
from typing import Optional

import dotenv
import matplotlib.pyplot as plt
import pandas as pd
from dune_client.client import DuneClient
from dune_client.query import QueryBase
from dune_client.types import QueryParameter, ParameterType
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, ConversationHandler, Application, filters, CallbackQueryHandler
from telegram.constants import ParseMode

# Load the environment variables
dotenv.load_dotenv(".env")

# Create a new Mongo DB client and connect to the server
mongo_client = MongoClient(os.getenv("MONGO_URI"), server_api=ServerApi('1'))

# Create a new Dune client
dune_client = DuneClient.from_env()

# Send a ping to confirm a successful connection
try:
    mongo_client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")

def hide_wallet_address(address: str) -> str:
    return f"{address[:4]}...{address[-4:]}"

async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Hello {update.effective_user.first_name}')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Hi! My name is Bark. I am a bot that can help you with your Bonk account. "
        "Please enter your public wallet key now."
    )
    return 0

async def save_public_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Please enter your public wallet key now.")
    return 0

async def public_key_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        mongo_client.bark.public_keys.insert_one(
            {"user_id": update.effective_user.id, "public_key": update.message.text}
        )
        keyboard = [
            [
                InlineKeyboardButton("Get Public Key", callback_data='get_public_key'),
                InlineKeyboardButton("Remove Public Key", callback_data='remove_public_key'),
            ],
            [
                InlineKeyboardButton("Total Volume", callback_data='total_volume'),
                InlineKeyboardButton("Latest Volumes", callback_data='latest_volumes'),
            ],
            [
                InlineKeyboardButton("Balances", callback_data='balances'),
                InlineKeyboardButton("PnL Graph", callback_data='pnl_graph'),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Thank you! Your public key has been stored. Choose an option:", reply_markup=reply_markup)
    except Exception as e:
        await update.message.reply_text(f"Error storing your public key: {e}")
    return ConversationHandler.END

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton("Get Public Key", callback_data='get_public_key'),
            InlineKeyboardButton("Remove Public Key", callback_data='remove_public_key'),
        ],
        [
            InlineKeyboardButton("Total Volume", callback_data='total_volume'),
            InlineKeyboardButton("Latest Volumes", callback_data='latest_volumes'),
        ],
        [
            InlineKeyboardButton("Balances", callback_data='balances'),
            InlineKeyboardButton("PnL Graph", callback_data='pnl_graph'),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query = update.callback_query
    await query.message.reply_text("Choose an option:", reply_markup=reply_markup)

async def get_public_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    public_key = mongo_client.bark.public_keys.find_one({"user_id": query.from_user.id})
    if public_key:
        await query.edit_message_text(f"Your public key is: {hide_wallet_address(public_key['public_key'])}")
    else:
        await query.edit_message_text("You have not saved your public key yet. Please save it with /save_public_key.")
    await show_menu(update, context)

async def remove_public_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        mongo_client.bark.public_keys.delete_many({"user_id": query.from_user.id})
        await query.edit_message_text("Your public key has been removed.")
    except Exception as e:
        await query.edit_message_text(f"Error removing your public key: {e}")
    await show_menu(update, context)

async def get_total_volume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        total_volume = dune_client.get_latest_result(3777885).result.rows[0]["Volume"]
        await query.edit_message_text(f"The total volume of Bonk is: {total_volume:.3f}")
    except Exception as e:
        await query.edit_message_text(f"Error fetching total volume: {e}")
    await show_menu(update, context)

async def get_latest_volumes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        query_result = dune_client.get_latest_result(3777907)
        sorted_result = sorted(query_result.result.rows, key=lambda x: x['Time'], reverse=True)
        latest_result_time = sorted_result[0]['Time']
        latest_results = [result for result in sorted_result if result['Time'] == latest_result_time]
        sorted_latest_results = sorted(latest_results, key=lambda x: x['Volume'], reverse=True)

        message = f"Latest Volumes for Bonk ({latest_result_time}):"
        for result in sorted_latest_results:
            message += f"\n{result['token_bought_symbol']} : {result['Volume']:.3f}"

        await query.edit_message_text(message)
    except Exception as e:
        await query.edit_message_text(f"Error fetching latest volumes: {e}")
    await show_menu(update, context)

async def get_balances(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_public_key = mongo_client.bark.public_keys.find_one({"user_id": query.from_user.id})
    if not user_public_key:
        await query.edit_message_text("You have not saved your public key yet. Please save it with /save_public_key.")
        return

    balances_query = QueryBase(
        name="Balances Query",
        query_id=3808006,
        params=[
            QueryParameter(
                name="Solana Wallet Address",
                value=user_public_key["public_key"],
                parameter_type=ParameterType.TEXT
            ),
        ]
    )

    total_portfolio_usd_query = QueryBase(
        name="Total Portfolio USD Query",
        query_id=3808045,
        params=[
            QueryParameter(
                name="Solana Wallet Address",
                value=user_public_key["public_key"],
                parameter_type=ParameterType.TEXT
            ),
        ]
    )

    total_portfolio_sol_query = QueryBase(
        name="Total Portfolio SOL Query",
        query_id=3815789,
        params=[
            QueryParameter(
                name="Solana Wallet Address",
                value=user_public_key["public_key"],
                parameter_type=ParameterType.TEXT
            ),
        ]
    )

    try:
        fetching_message = await query.edit_message_text("Please wait while I fetch your balances.")
        
        # Run all queries concurrently
        balances_result = dune_client.run_query(query=balances_query, performance='medium')
        total_usd_result = dune_client.run_query(query=total_portfolio_usd_query, performance='medium')
        total_sol_result = dune_client.run_query(query=total_portfolio_sol_query, performance='medium')

        # Debug: Print the results to check the returned structure
        print("Balances Result:", balances_result.result.rows)
        print("Total USD Result:", total_usd_result.result.rows)
        print("Total SOL Result:", total_sol_result.result.rows)

        balances_data = balances_result.result.rows

        # Sort balances data by token value in USD
        balances_data = sorted(balances_data, key=lambda x: float(x['token_value'] or 0), reverse=True)

        # Create a pie chart
        tokens = [row['token_symbol'][:6] for row in balances_data]  # truncate token symbols to 6 characters
        token_values = [float(row['token_value']) for row in balances_data if row['token_value'] is not None]

        plt.figure(figsize=(10, 6))  # Increase the figure size
        wedges, texts, autotexts = plt.pie(
            token_values,
            labels=[f"{token} (${value:.2f})" for token, value in zip(tokens, token_values)],
            autopct='%1.1f%%',
            startangle=140
        )

        # Improve text positioning
        for text in texts + autotexts:
            text.set_fontsize(10)

        plt.title('Token Balances')
        plt.tight_layout()

        buf = BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()

        # Send the pie chart
        await context.bot.send_photo(chat_id=query.message.chat_id, photo=buf)

        # Prepare the message
        messages = f"Balances for your wallet address ({hide_wallet_address(user_public_key['public_key'])}):"

        # Total portfolio value
        try:
            total_usd_value = total_usd_result.result.rows[0].get("Account_USD_Value", "N/A")
        except (IndexError, KeyError) as e:
            print(f"Error fetching total_usd_value: {e}")
            total_usd_value = "N/A"

        try:
            total_sol_value = total_sol_result.result.rows[0].get("Account_SOL_Value", "N/A")
        except (IndexError, KeyError) as e:
            print(f"Error fetching total_sol_value: {e}")
            total_sol_value = "N/A"

        messages += f"\n\n<b>Total Portfolio Value:</b>\n\n"
        messages += f"USD: ${total_usd_value:.2f}" if total_usd_value != "N/A" else "USD: N/A"
        messages += f"\nSOL: {total_sol_value:.3f}" if total_sol_value != "N/A" else "\nSOL: N/A"

        messages += f"\n\n<b>Token Symbol</b> : Token Balance : <b>Total Token Value (USD)</b>"
        for row in balances_data:
            if row['token_value']:
                messages += f"\n<b>{row['token_symbol']}</b> : {float(row['token_balance']):.3f} : <b>${row['token_value']:.2f}</b>"
            else:
                messages += f"\n<b>{row['token_symbol']}</b> : {float(row['token_balance']):.3f} : N/A"

        await fetching_message.delete()
        await context.bot.send_message(chat_id=query.message.chat_id, text=messages, parse_mode=ParseMode.HTML)
    except Exception as e:
        await query.edit_message_text(f"Error fetching balances: {e}")
    await show_menu(update, context)

async def get_pnl_graph(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_public_key = mongo_client.bark.public_keys.find_one({"user_id": query.from_user.id})
    if not user_public_key:
        await query.edit_message_text("You have not saved your public key yet. Please save it with /save_public_key.")
        return

    pnl_query = QueryBase(
        name="PnL Query",
        query_id=3852029,  # Use the query ID provided
        params=[
            QueryParameter(
                name="Solana Wallet Address",
                value=user_public_key["public_key"],
                parameter_type=ParameterType.TEXT
            ),
        ]
    )

    try:
        pnl_result = dune_client.run_query(query=pnl_query, performance='medium')
        pnl_rows = pnl_result.result.rows
        if not pnl_rows:
            await query.edit_message_text("No PnL data available.")
            return
    except Exception as e:
        await query.edit_message_text(f"Error fetching PnL data: {e}")
        return

    df_pnl = pd.DataFrame(pnl_rows)
    df_pnl['total_pnl_usd'] = df_pnl['total_pnl_usd'].astype(float)

    df_pnl = df_pnl.sort_values(by='total_pnl_usd', ascending=True)

    plt.figure(figsize=(10, 6))
    bars = plt.bar(df_pnl['token_symbol'], df_pnl['total_pnl_usd'], color=['red' if x < 0 else 'blue' for x in df_pnl['total_pnl_usd']])
    plt.xlabel('Token')
    plt.ylabel('PnL (USD)')
    plt.title('PnL for each Token')
    plt.xticks(rotation=45)
    plt.tight_layout()

    for bar in bars:
        if bar.get_height() < 0:
            bar.set_y(bar.get_height())

    bio = BytesIO()
    plt.savefig(bio, format='png')
    bio.seek(0)
    plt.close()

    total_pnl_usd = df_pnl['total_pnl_usd'].sum()
    pnl_status = "+" if total_pnl_usd > 0 else "-"

    await context.bot.send_photo(chat_id=query.message.chat_id, photo=bio, caption=f"PnL for each Token\n\nTotal PnL (USD): {pnl_status}${abs(total_pnl_usd):.2f}")

    pnl_message = "<b>Detailed PnL Data:</b>\n<hr>\n"
    for _, row in df_pnl.iterrows():
        pnl_message += f"<b>{row['token_symbol']}</b>: {row['total_pnl_usd']:.2f} $\n"

    await context.bot.send_message(chat_id=query.message.chat_id, text=pnl_message, parse_mode=ParseMode.HTML)
    await show_menu(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Action cancelled.")
    return ConversationHandler.END

def main() -> None:
    application = Application.builder().token(os.getenv("TG_TOKEN")).build()

    start_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            0: [
                MessageHandler(
                    filters.Regex("^[1-9A-HJ-NP-Za-km-z]{32,44}$"), public_key_input
                ),
            ],
        },
        fallbacks=[MessageHandler(filters.TEXT, cancel)],
    )

    save_key_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("save_public_key", save_public_key)],
        states={
            0: [
                MessageHandler(
                    filters.Regex("^[1-9A-HJ-NP-Za-km-z]{32,44}$"), public_key_input
                ),
            ],
        },
        fallbacks=[MessageHandler(filters.TEXT, cancel)],
    )

    application.add_handler(start_conv_handler)
    application.add_handler(save_key_conv_handler)
    application.add_handler(CallbackQueryHandler(get_public_key, pattern='get_public_key'))
    application.add_handler(CallbackQueryHandler(remove_public_key, pattern='remove_public_key'))
    application.add_handler(CallbackQueryHandler(get_total_volume, pattern='total_volume'))
    application.add_handler(CallbackQueryHandler(get_latest_volumes, pattern='latest_volumes'))
    application.add_handler(CallbackQueryHandler(get_balances, pattern='balances'))
    application.add_handler(CallbackQueryHandler(get_pnl_graph, pattern='pnl_graph'))
    application.add_handler(CommandHandler("hello", hello))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
