import sys
import subprocess
import time
import signal
import pandas as pd

import ViennaRNA
from rna_design_algorithms.sample_based.IncaRNAtion.utils.sample import sample_incarnation

def call_incarnation(target_structure, constraints=None, tries=1, GCcontent=None, time_limit=None, save_file="incarnation_result"):
    """
    Use incarnation sampling as a start sequence of RNAinverse.

    Parameters:
    - target_structure (str): The target RNA secondary structure in dot-bracket notation.
    - constraints (str): The sequence constraints of results
    - tries(int): number of sequences you want to generate (same target structure)
    - GCcontent (float): design sequences' GC content you want to reach
    - time_limit (int): seconds, time limitation of designing
    - save_file (str): save path

    Returns:
    - sequences (list[str]): list of designed sequences
    """
    if not target_structure:
        print('Error: target structure is empty!')
        sys.exit(1)

    if time_limit is not None:
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(time_limit)  # start timer

    try:
        sampling_start = time.time()  # start sampling
        # sample
        init_seqs = sample_incarnation(target_structure, constraints, tries, GCcontent)

        sampling_end = time.time()  # end sampling
        sampling_time = sampling_end - sampling_start

        # RNAinverse
        output_Seq = []  # designed sequences list
        output_Dis = []  # distances between designed seqs' structure and target structure
        time_consumes = []  # time consume for each design loop

        for i in range(tries):
            start_time = time.time()
            seq, dis = ViennaRNA.inverse_fold(init_seqs[i], target_structure)
            end_time = time.time()

            time_consumes.append(sampling_time + end_time - start_time)
            output_Seq.append(seq)
            output_Dis.append(dis)
    except TimeoutSignal:
        # time limit has reached, save empty file
        data = {'sequence': [], 'time': [], 'distance': []}
        df = pd.DataFrame(data)
        save_file = 'results/' + save_file + '.pkl'
        df.to_pickle(save_file)
        return []
    except ZeroDivisionError:
        # sometimes incarnation sampling will raise this error
        data = {'sequence': [], 'time': [], 'distance': []}
        df = pd.DataFrame(data)
        save_file = 'results/' + save_file + '.pkl'
        df.to_pickle(save_file)
        return []

    # save to file
    data = {'sequence': output_Seq, 'time': time_consumes, 'distance': output_Dis}
    df = pd.DataFrame(data)
    save_file = 'results/' + save_file + '.pkl'
    df.to_pickle(save_file)

    return output_Seq

class TimeoutSignal(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutSignal("time's up!")

if __name__ == "__main__":
    target_structure = "(((....)))((...))"
    tries = 10
    output_seq = call_incarnation(target_structure, tries=tries)

    for i in range(tries):
        print(output_seq[i])

    # print("----- RNAinverse without start strings --------")
    # for i in range(tries):
    #     start = 'NNNNNNNNNNNNNNNNN'  # without sequence constraints
    #     seq, dis = ViennaRNA.inverse_fold(start, target_structure)
    #     print(seq, dis)



