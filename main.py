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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! My name is Bark. Welcome to the bot that can help you with your Bonk account. "
        "To use this application, please save your public key using the /save_public_key command."
    )

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
                InlineKeyboardButton("PnL Details", callback_data='pnl_graph'),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Thank you! Your public key has been stored. Choose an option:", reply_markup=reply_markup)
    except Exception as e:
        await update.message.reply_text(f"Error storing your public key: {e}")
    return ConversationHandler.END

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = "Choose an option:") -> None:
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
            InlineKeyboardButton("PnL Details", callback_data='pnl_graph'),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)

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
    
    user_public_key = mongo_client.bark.public_keys.find_one({"user_id": query.from_user.id})
    if not user_public_key:
        await query.edit_message_text("You have not saved your public key yet. Please save it with /save_public_key.")
        return

    total_volume_query = QueryBase(
        name="Total Volume Query",
        query_id=3777885,  # Replace with your actual query ID
        params=[
            QueryParameter(
                name="Solana Wallet Address",
                value=user_public_key["public_key"],
                parameter_type=ParameterType.TEXT
            ),
        ]
    )

    try:
        fetching_message = await query.edit_message_text("Please wait while I fetch your total volume.")
        
        result = dune_client.run_query(query=total_volume_query, performance='medium')
        total_volume = result.result.rows[0]["Volume"]
        await fetching_message.edit_text(f"Your Wallet Total Volume is: ${total_volume:.3f}")
        await show_menu(update, context)
    except Exception as e:
        await fetching_message.edit_text(f"Error fetching total volume: {e}")

async def get_latest_volumes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    user_public_key = mongo_client.bark.public_keys.find_one({"user_id": query.from_user.id})
    if not user_public_key:
        await query.edit_message_text("You have not saved your public key yet. Please save it with /save_public_key.")
        return

    latest_volumes_query = QueryBase(
        name="Latest Volumes Query",
        query_id=3777907,  # Replace with your actual query ID
        params=[
            QueryParameter(
                name="Solana Wallet Address",
                value=user_public_key["public_key"],
                parameter_type=ParameterType.TEXT
            ),
        ]
    )

    try:
        fetching_message = await query.edit_message_text("Please wait while I fetch the latest volumes.")

        result = dune_client.run_query(query=latest_volumes_query, performance='medium')
        sorted_result = sorted(result.result.rows, key=lambda x: x['Time'], reverse=True)
        latest_result_time = sorted_result[0]['Time']
        latest_results = [res for res in sorted_result if res['Time'] == latest_result_time]
        sorted_latest_results = sorted(latest_results, key=lambda x: x['Volume'], reverse=True)

        message = f"Latest Volumes ({latest_result_time}):"
        for res in sorted_latest_results:
            message += f"\n{res['token_bought_symbol']} : {res['Volume']:.3f}"

        await fetching_message.edit_text(message)
        await show_menu(update, context)
    except Exception as e:
        await fetching_message.edit_text(f"Error fetching latest volumes: {e}")

async def get_balances(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_public_key = mongo_client.bark.public_keys.find_one({"user_id": query.from_user.id})
    if not user_public_key:
        await query.edit_message_text("You have not saved your public key yet. Please save it with /save_public_key.")
        return

    balances_query = QueryBase(
        name="Balances Query",
        query_id=3852195,  # Updated query ID
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
        
        # Run balances query
        balances_result = dune_client.run_query(query=balances_query, performance='medium')
        balances_df = pd.DataFrame(balances_result.result.rows)

        # Debug: Print the results to check the returned structure
        print("Balances Result:", balances_df)

        balances_data = balances_df.to_dict(orient='records')

        # Sort balances data by token value in USD, handling NaN values
        balances_data = sorted(balances_data, key=lambda x: float(x['token_usd_value'] or 0), reverse=True)

        # Calculate total USD value
        total_usd_value = sum(float(row['token_usd_value']) if pd.notna(row['token_usd_value']) else 0 for row in balances_data)

        # Filter out tokens with less than 1% of the total value
        token_values = [float(row['token_usd_value']) if pd.notna(row['token_usd_value']) else 0 for row in balances_data]
        tokens = [row['token_symbol'][:6] for row in balances_data]  # truncate token symbols to 6 characters

        token_percentages = [value / total_usd_value * 100 for value in token_values]
        filtered_tokens = [(token, value) for token, value, percentage in zip(tokens, token_values, token_percentages) if percentage >= 1]

        # Create a pie chart
        plt.figure(figsize=(10, 6))  # Increase the figure size
        wedges, texts, autotexts = plt.pie(
            [value for _, value in filtered_tokens],
            labels=[f"{token} (${value:.2f})" for token, value in filtered_tokens],
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

        messages += f"\n\n<b>Total Portfolio Value:</b>\n\n"
        messages += f"USD: ${total_usd_value:.2f}"

        messages += f"\n\n<b>Token Symbol</b> : Token Balance : <b>Total Token Value (USD)</b>"
        for row in balances_data:
            token_balance = float(row['token_balance']) if pd.notna(row['token_balance']) else 0
            token_value = float(row['token_usd_value']) if pd.notna(row['token_usd_value']) else 0
            messages += f"\n<b>{row['token_symbol']}</b> : {token_balance:.3f} : <b>${token_value:.2f}</b>"

        await fetching_message.delete()
        await context.bot.send_message(chat_id=query.message.chat_id, text=messages, parse_mode=ParseMode.HTML)
        await show_menu(update, context)
    except Exception as e:
        await query.edit_message_text(f"Error fetching balances: {e}")

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
        fetching_message = await query.edit_message_text("Please wait while I fetch your PnL data.")

        pnl_result = dune_client.run_query(query=pnl_query, performance='medium')
        pnl_df = pd.DataFrame(pnl_result.result.rows)
        if pnl_df.empty:
            await fetching_message.edit_text("No PnL data available.")
            return

        pnl_df['total_pnl_usd'] = pnl_df['total_pnl_usd'].astype(float)
        pnl_df = pnl_df.sort_values(by='total_pnl_usd', ascending=True)

        plt.figure(figsize=(10, 6))
        bars = plt.bar(pnl_df['token_symbol'], pnl_df['total_pnl_usd'], color=['red' if x < 0 else 'blue' for x in pnl_df['total_pnl_usd']])
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

        total_pnl_usd = pnl_df['total_pnl_usd'].sum()
        pnl_status = "+" if total_pnl_usd > 0 else "-"

        await context.bot.send_photo(chat_id=query.message.chat_id, photo=bio, caption=f"PnL for each Token\n\nTotal PnL (USD): {pnl_status}${abs(total_pnl_usd):.2f}")

        pnl_message = "<b>Detailed PnL Data:</b>\n"
        for _, row in pnl_df.iterrows():
            pnl_message += f"<b>{row['token_symbol']}</b>: {row['total_pnl_usd']:.2f} $\n"

        await fetching_message.delete()
        await context.bot.send_message(chat_id=query.message.chat_id, text=pnl_message, parse_mode=ParseMode.HTML)
        await show_menu(update, context)
    except Exception as e:
        await fetching_message.edit_text(f"Error fetching PnL data: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Please save valid public key. Save it with /save_public_key.")
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
