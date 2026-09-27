import json

with open("data_process/results/gen_asteria_feature_results.json", "rb") as f:
    contents = json.load(f)

for res in contents:
    errcode = res["errcode"]
    bin_path = res["bin_path"]
    errmsg = res["errmsg"]
    if errcode == 0:
        continue
    else:
        print(f"------ ERROR (CODE {errcode}) ------")
        print(f"Bin path: {bin_path}")
        print(f"Error message: {errmsg}")