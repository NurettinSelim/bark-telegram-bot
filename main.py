import os

import dotenv
from dune_client.client import DuneClient
from dune_client.query import QueryBase
from dune_client.types import QueryParameter, ParameterType
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, ConversationHandler, \
    Application, filters

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
    print(e)


async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Hello {update.effective_user.first_name}')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send message on `/start` and wait for public wallet key input."""
    await update.message.reply_text(
        "Hi! My name is Bark. I am a bot that can help you with your Bonk account. "
        "Please enter your public wallet key now."
    )
    return 0


async def save_public_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Get the public wallet key."""
    await update.message.reply_text(
        "Please enter your public wallet key now."
    )

    return 0


async def public_key_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the public wallet key."""
    mongo_client.bark.public_keys.insert_one(
        {
            "user_id": update.effective_user.id,
            "public_key": update.message.text,
        }
    )

    await update.message.reply_text(
        "Thank you! Your public key stored."
    )

    return ConversationHandler.END


async def get_public_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Get the public wallet key."""
    public_key = mongo_client.bark.public_keys.find_one(
        {
            "user_id": update.effective_user.id,
        }
    )

    if not public_key:
        await update.message.reply_text(
            "You have not saved your public key yet. Please save it with /save_public_key."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"Your public key is: {public_key['public_key']}"
    )

    return ConversationHandler.END


async def remove_public_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Remove the public wallet key."""
    mongo_client.bark.public_keys.delete_many(
        {
            "user_id": update.effective_user.id,
        }
    )

    await update.message.reply_text(
        "Your public key removed."
    )

    return ConversationHandler.END


async def get_total_volume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get the total volume of the Bonk."""
    total_volume = dune_client.get_latest_result(3777885).result.rows[0]["Volume"]

    await update.message.reply_text(
        f"The total volume of the Bonk is: {total_volume:.3f}"
    )


async def get_latest_volumes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get the latest volumes of the Bonk."""
    query_result = dune_client.get_latest_result(3777907)
    sorted_result = sorted(query_result.result.rows, key=lambda x: x['Time'], reverse=True)
    latest_result_time = sorted_result[0]['Time']
    latest_results = [result for result in sorted_result if result['Time'] == latest_result_time]
    sorted_latest_results = sorted(latest_results, key=lambda x: x['Volume'], reverse=True)

    message = f"Latest Volumes for Bonk ({latest_result_time}):"
    for result in sorted_latest_results:
        message += f"\n{result['token_bought_symbol']} : {result['Volume']:.3f}"

    await update.message.reply_text(message)


async def get_balances(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Get the balances of the Solana wallet address."""
    user_public_key = mongo_client.bark.public_keys.find_one(
        {
            "user_id": update.effective_user.id,
        }
    )
    if not user_public_key:
        await update.message.reply_text(
            "You have not saved your public key yet. Please save it with /save_public_key."
        )
        return ConversationHandler.END

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

    fetching_message = await update.message.reply_text(
        "Please wait while I fetch your balances."
    )

    result = dune_client.run_query(query=query, performance='medium')

    messages = f"Balances for your wallet address ({user_public_key['public_key']}):"
    messages += f"\nToken Symbol : Token Balance : Total Token Value(USD)"
    for row in result.result.rows:
        if row['token_value']:
            messages += f"\n{row['token_symbol']} : {float(row['token_balance']):.3f} : {row['token_value']:.3f}"
        else:
            messages += f"\n{row['token_symbol']} : {float(row['token_balance']):.3f} : N/A"

    await fetching_message.delete()
    await update.message.reply_text(messages)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    await update.message.reply_text("Action cancelled.")

    return ConversationHandler.END

def main() -> None:
    """Run the bot."""
    # Create the Application and pass it your bot's token.
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

    # Bonk Public Key Handlers
    application.add_handler(start_conv_handler)
    application.add_handler(save_key_conv_handler)
    application.add_handler(CommandHandler("get_public_key", get_public_key))
    application.add_handler(CommandHandler("remove_public_key", remove_public_key))

    # Dune Handlers
    application.add_handler(CommandHandler("total_volume", get_total_volume))
    application.add_handler(CommandHandler("latest_volumes", get_latest_volumes))
    application.add_handler(CommandHandler("balances", get_balances))

    # Test handlers
    application.add_handler(CommandHandler("hello", hello))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
