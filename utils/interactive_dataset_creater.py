import argparse
from enum import Enum
import glob
import pandas as pd

class Operations(str, Enum):
    COMBINE = "combine"
    BINARIZE = "binarize"
    QUIT = "quit"
    OUTPUT = "output"

def receive_operation():
    print("Provide an operation")
    operation = input()
    operation_components = operation.split(' ', 1)
    return operation_components[0], operation_components[1].split() if len(operation_components) > 1 else None


def combine(dataset_dfs):
    return pd.concat(dataset_dfs)

def binarize(dataframe, positive_class):
    dataframe.loc[dataset_df['label_type'] != positive_class, 'label_type'] = 0
    dataframe.loc[dataset_df['label_type'] == positive_class, 'label_type'] = 1

def output(dataframe, output_path):
    dataframe.to_csv(output_path, index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv_folder", default="../datasets")
    args = parser.parse_args()

    dataset_csv_folder = args.csv_folder

    # get a list of dataset csvs
    csv_list = glob.glob(dataset_csv_folder + "/*.csv")
    print("The following CSVs are available:")
    for i in range(len(csv_list)):
        print(f'{i + 1}: {csv_list[i]}')
    
    print()

    # give list of options
    print("Options:")
    for operation in Operations:
        print(operation.value)

    print()

    output_df = None
    
    while True:
        command, arguments = receive_operation()
        print()

        print(command)
        print(arguments)

        if command == Operations.QUIT:
            break
        elif command == Operations.COMBINE:
            dataframes = [output_df] if output_df is not None else []
            for i in arguments:
                dataset_df = pd.read_csv(csv_list[int(i) - 1])
                dataframes.append(dataset_df)
            combined_df = combine(dataframes)
            output_df = combined_df
        elif command == Operations.BINARIZE:
            positive_class = int(arguments[0])
            if output_df is not None:
                binarize(output_df, positive_class)
        elif command == Operations.OUTPUT:
            output_path = arguments[0]
            if output_df is not None:
                output(output_df, output_path)
                output_df = None
        else:
            print("Unrecognized operation")

        

