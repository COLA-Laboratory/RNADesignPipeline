import subprocess
from utilis.RNA_fold import predict_structure, str_distance

def call_rnainverse(target_structure):
    """
    Call RNAinverse from ViennaRNA package to find an RNA sequence that folds into the target structure.
    Parameters:
    - target_structure (str): The target RNA secondary structure in dot-bracket notation.
    Returns:
    - str: An RNA sequence that is predicted to fold into the target structure.
    """
    # Prepare the RNAinverse command.
    # Assuming RNAinverse accepts the target structure from standard input.
    command = ['RNAinverse']
    # Execute the command with the target structure as input.
    process = subprocess.run(command, input=target_structure, text=True, capture_output=True, check=True)

    # Extract the RNA sequence from the command output.
    # Note: You might need to adjust the parsing depending on the RNAinverse output format.
    rna_sequence = process.stdout.strip()
    structure, mfe, computation_time = predict_structure(rna_sequence)
    distance = str_distance(structure, target_structure)
    return rna_sequence, structure, distance

if __name__ == '__main__':
    # Example usage:
    target_structure = "(((....)))((...))"
    rna_sequence, structure, distance = call_rnainverse(target_structure)
    print(f"RNA sequence that folds into the target structure: {rna_sequence}")
