import dotenv
from dune_client.client import DuneClient
from dune_client.query import QueryBase
from dune_client.types import QueryParameter, ParameterType

dotenv.load_dotenv(".env")

dune = DuneClient.from_env()

# query = QueryBase(
#     name="Sample Query",
#     query_id=1215383,
# )
#
# result = dune.run_query(
#     query = query,
#     performance = 'large' # optionally define which tier to run the execution on (default is "medium")
# )
#
# # go over the results returned
# for row in result.result.rows:
#     print (row) # as an example we print the rows


# query_result = dune.get_latest_result(3777907)
#
# print(query_result.result.rows)
# sorted_result = sorted(query_result.result.rows, key=lambda x: x['Time'], reverse=True)
# latest_result_time = sorted_result[0]['Time']
# latest_results = [result for result in sorted_result if result['Time'] == latest_result_time]
# sorted_latest_results = sorted(latest_results, key=lambda x: x['Volume'], reverse=True)
# #pretty print the results
# print(f"Latest Volumes for BonkBot ({latest_result_time}):")
# for result in sorted_latest_results:
#     print(f"{result['token_bought_symbol']} - Volume: {result['Volume']:.2f}" )


query = QueryBase(
    name="Balances Query",
    query_id=3808006,
    params=[
        QueryParameter(
            name="Solana Wallet Address", value="7eRoDPvmmxPgswXw3hRYSLS4NEhwMgjjAxw3re8zbUCQ",
            parameter_type=ParameterType.TEXT
        ),
    ]
)

result = dune.run_query(query=query)

for row in result.result.rows:
    print(row)
