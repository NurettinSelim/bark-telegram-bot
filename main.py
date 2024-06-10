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
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, ConversationHandler, Application, filters

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
        await update.message.reply_text("Thank you! Your public key has been stored.")
    except Exception as e:
        await update.message.reply_text(f"Error storing your public key: {e}")
    return ConversationHandler.END


async def get_public_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    public_key = mongo_client.bark.public_keys.find_one({"user_id": update.effective_user.id})
    if public_key:
        await update.message.reply_text(f"Your public key is: {hide_wallet_address(public_key['public_key'])}")
    else:
        await update.message.reply_text("You have not saved your public key yet. Please save it with /save_public_key.")


async def remove_public_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        mongo_client.bark.public_keys.delete_many({"user_id": update.effective_user.id})
        await update.message.reply_text("Your public key has been removed.")
    except Exception as e:
        await update.message.reply_text(f"Error removing your public key: {e}")


async def get_total_volume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        total_volume = dune_client.get_latest_result(3777885).result.rows[0]["Volume"]
        await update.message.reply_text(f"The total volume of Bonk is: {total_volume:.3f}")
    except Exception as e:
        await update.message.reply_text(f"Error fetching total volume: {e}")


async def get_latest_volumes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query_result = dune_client.get_latest_result(3777907)
        sorted_result = sorted(query_result.result.rows, key=lambda x: x['Time'], reverse=True)
        latest_result_time = sorted_result[0]['Time']
        latest_results = [result for result in sorted_result if result['Time'] == latest_result_time]
        sorted_latest_results = sorted(latest_results, key=lambda x: x['Volume'], reverse=True)

        message = f"Latest Volumes for Bonk ({latest_result_time}):"
        for result in sorted_latest_results:
            message += f"\n{result['token_bought_symbol']} : {result['Volume']:.3f}"

        await update.message.reply_text(message)
    except Exception as e:
        await update.message.reply_text(f"Error fetching latest volumes: {e}")


async def get_balances(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_public_key = mongo_client.bark.public_keys.find_one({"user_id": update.effective_user.id})
    if not user_public_key:
        await update.message.reply_text("You have not saved your public key yet. Please save it with /save_public_key.")
        return

    query = QueryBase(
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

    try:
        fetching_message = await update.message.reply_text("Please wait while I fetch your balances.")
        result = dune_client.run_query(query=query, performance='medium')
        balances_data = result.result.rows

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
        await update.message.reply_photo(photo=buf)

        # Send the text message
        messages = f"Balances for your wallet address ({hide_wallet_address(user_public_key['public_key'])}):"
        messages += f"\nToken Symbol : Token Balance : Total Token Value (USD)"
        for row in balances_data:
            if row['token_value']:
                messages += f"\n{row['token_symbol']} : {float(row['token_balance']):.3f} : ${row['token_value']:.2f}"
            else:
                messages += f"\n{row['token_symbol']} : {float(row['token_balance']):.3f} : N/A"

        await fetching_message.delete()
        await update.message.reply_text(messages)
    except Exception as e:
        await update.message.reply_text(f"Error fetching balances: {e}")


async def get_pnl_graph(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_public_key = mongo_client.bark.public_keys.find_one({"user_id": update.effective_user.id})
    if not user_public_key:
        await update.message.reply_text("You have not saved your public key yet. Please save it with /save_public_key.")
        return

    query = QueryBase(
        name="PnL Query",
        query_id=3814999,  # Use the query ID provided
        params=[
            QueryParameter(
                name="Solana Wallet Address",
                value=user_public_key["public_key"],
                parameter_type=ParameterType.TEXT
            ),
        ]
    )

    try:
        result = dune_client.run_query(query=query, performance='medium')
        rows = result.result.rows
        if not rows:
            await update.message.reply_text("No PnL data available.")
            return
    except Exception as e:
        await update.message.reply_text(f"Error fetching PnL data: {e}")
        return

    # Convert results to DataFrame
    df = pd.DataFrame(rows)
    df['pnl_usd'] = df['pnl_usd'].astype(float)

    # Plot PnL Bar Chart
    plt.figure(figsize=(10, 6))
    plt.bar(df['token'], df['pnl_usd'], color='blue')
    plt.xlabel('Token')
    plt.ylabel('PnL (USD)')
    plt.title('PnL for each Token')
    plt.xticks(rotation=45)
    plt.tight_layout()

    # Save bar chart to a BytesIO object
    bio_bar = BytesIO()
    plt.savefig(bio_bar, format='png')
    bio_bar.seek(0)
    plt.close()

    # Plot PnL Line Graph
    plt.figure(figsize=(10, 6))
    plt.plot(df['token'], df['pnl_usd'], marker='o', linestyle='-', color='blue')
    plt.xlabel('Token')
    plt.ylabel('PnL (USD)')
    plt.title('PnL for each Token')
    plt.xticks(rotation=45)
    plt.tight_layout()

    # Save line graph to a BytesIO object
    bio_line = BytesIO()
    plt.savefig(bio_line, format='png')
    bio_line.seek(0)
    plt.close()

    # Send the plots to the user
    await update.message.reply_photo(photo=bio_bar, caption="PnL for each Token (Bar Chart)")
    await update.message.reply_photo(photo=bio_line, caption="PnL for each Token (Line Graph)")



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
    application.add_handler(CommandHandler("get_public_key", get_public_key))
    application.add_handler(CommandHandler("remove_public_key", remove_public_key))
    application.add_handler(CommandHandler("total_volume", get_total_volume))
    application.add_handler(CommandHandler("latest_volumes", get_latest_volumes))
    application.add_handler(CommandHandler("balances", get_balances))
    application.add_handler(CommandHandler("pnl_graph", get_pnl_graph))  # Add this line
    application.add_handler(CommandHandler("hello", hello))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
