import time
import math

from itertools import product
from dataclasses import dataclass
from distance import hamming
from collections import Counter

import numpy as np
from tensorforce.environments import Environment

import requests
import re

from RNA import fold

def new_fold(sequence_to_fold):
    # Use ViennaFold at the moment
    seq, _ = fold(sequence_to_fold)
    return seq
    # FM Code
    print(sequence_to_fold)
    print(fold(sequence_to_fold))
    url = 'http://10.207.119.13:5000/ss_predict'
    seq = sequence_to_fold
    data = {'seq': [seq]}
    response = requests.post(url, json=data)
    print("response: ", response.json())
    if response.status_code == 200:
        return ''.join(response.json()["predicted_sequence"])

    #else:
        # Use ViennaFold instead
    seq, _ = fold(sequence_to_fold)
    return seq

def sequence_diversity_loss(count, n=3):
    """
    Maps the raw counts of appearances of the same sequences to the interval [0,1].

    Using the same formula as Alphafold2 for the cluster_deletion_value feature:

    2/\pi * arctan(d/3), where d are the raw counts.
    """
    # count = len(env_config['predictions'][prediction])

    return (2 / math.pi) * math.atan((count / n))



@dataclass
class RnaDesignEnvironmentConfig:
    """
    Dataclass for the configuration of the environment.

    Default values describe:
        mutation_threshold: Defines the minimum distance needed before applying the local
            improvement step.
        reward_exponent: A parameter to shape the reward function.
        state_radius: The state representation is a (2*<state_radius> + 1)-gram
            at each position.
        use_conv: Bool to state if a convolutional network is used or not.
        use_embedding: Bool to state if embedding is used or not.
    """

    mutation_threshold: int = 5
    reward_exponent: float = 1.0
    state_radius: int = 5
    use_conv: bool = True
    use_embedding: bool = False
    diversity_loss: bool = False


def _string_difference_indices(s1, s2):
    """
    Returns all indices where s1 and s2 differ.

    Args:
        s1: The first sequence.
        s2: The second sequence.

    Returns:
        List of indices where s1 and s2 differ.
    """
    return [index for index in range(len(s1)) if s1[index] != s2[index]]


def _encode_dot_bracket(secondary, env_config):
    """
    Encode the dot_bracket notated target structure. The encoding can either be binary
    or by the embedding layer.

    Args:
        secondary: The target structure in dot_bracket notation.
        env_config: The configuration of the environment.

    Returns:
        List of encoding for each site of the padded target structure.
    """
    padding = "=" * env_config.state_radius
    padded_secondary = padding + secondary + padding

    if env_config.use_embedding:
        site_encoding = {".": 0, "(": 1, ")": 2, "=": 3}
    else:
        site_encoding = {".": 0, "(": 1, ")": 1, "=": 0}

    # Sites corresponds to 1 pixel with 1 channel if convs are applied directly
    if env_config.use_conv and not env_config.use_embedding:
        return [[site_encoding[site]] for site in padded_secondary]
    return [site_encoding[site] for site in padded_secondary]


def _encode_pairing(secondary):
    """TODO
    """
    pairing_encoding = [None] * len(secondary)
    stack = []
    for index, symbol in enumerate(secondary, 0):
        if symbol == "(":
            stack.append(index)
        elif symbol == ")":
            paired_site = stack.pop()
            pairing_encoding[paired_site] = index
            pairing_encoding[index] = paired_site
    return pairing_encoding


class _Target(object):
    """TODO
    Class of the target structure. Provides encodings and id.
    """

    _id_counter = 0

    def __init__(self, dot_bracket, env_config, target_id=None):
        """
        Initialize a target structure.

        Args:
             dot_bracket: dot_bracket encoded target structure.
             env_config: The environment configuration.
        """
        _Target._id_counter += 1
        if target_id is None:
            self.id = _Target._id_counter  # For processing results
        else:
            self.id = target_id
        self.dot_bracket = dot_bracket
        self._pairing_encoding = _encode_pairing(self.dot_bracket)
        self.padded_encoding = _encode_dot_bracket(self.dot_bracket, env_config)

    def __len__(self):
        return len(self.dot_bracket)

    def get_paired_site(self, site):
        """
        Get the paired site for <site> (base pair).

        Args:
            site: The site to check the pairing site for.

        Returns:
            The site that pairs with <site> if exists.TODO
        """
        return self._pairing_encoding[site]


class _Design(object):
    """
    Class of the designed candidate solution.
    """

    action_to_base = {0: "G", 1: "A", 2: "U", 3: "C"}
    action_to_pair = {0: "GC", 1: "CG", 2: "AU", 3: "UA"}

    def __init__(self, length=None, primary=None):
        """
        Initialize a candidate solution.

        Args:
            length: The length of the candidate solution.
            primary: The sequence of the candidate solution.
        """
        if primary:
            self._primary_list = primary
        else:
            self._primary_list = [None] * length
        self._dot_bracket = None
        self._current_site = 0

    def get_mutated(self, mutations, sites):
        """
        Locally change the candidate solution.

        Args:
            mutations: Possible mutations for the specified sites
            sites: The sites to be mutated

        Returns:
            A Design object with the mutated candidate solution.
        """
        mutatedprimary = self._primary_list.copy()
        for site, mutation in zip(sites, mutations):
            mutatedprimary[site] = mutation
        return _Design(primary=mutatedprimary)

    def assign_sites(self, action, site, paired_site=None):
        """
        Assign nucleotides to sites for designing a candidate solution.

        Args:
            action: The agents action to assign a nucleotide.
            site: The site to which the nucleotide is assigned to.
            paired_site: defines if the site is assigned with a base pair or not.
        """
        self._current_site += 1
        if paired_site:
            base_current, base_paired = self.action_to_pair[action]
            self._primary_list[site] = base_current
            self._primary_list[paired_site] = base_paired
        else:
            self._primary_list[site] = self.action_to_base[action]

    @property
    def first_unassigned_site(self):
        try:
            while self._primary_list[self._current_site] is not None:
                self._current_site += 1
            return self._current_site
        except IndexError:
            return None

    @property
    def primary(self):
        return "".join(self._primary_list)


def _random_epoch_gen(data):
    """
    Generator to get epoch data.

    Args:
        data: The targets of the epoch
    """
    while True:
        for i in np.random.permutation(len(data)):
            yield data[i]


@dataclass
class EpisodeInfo:
    """
    Information class.
    """

    __slots__ = ["target_id",
                 "time",
                 "normalized_hamming_distance",
                 "hamming_distance",
                 "structure",
                 "sequence",
                 ]
    target_id: int
    time: float
    normalized_hamming_distance: float
    hamming_distance: int
    structure: str
    sequence: str


class RnaDesignEnvironment(Environment):
    """
    The environment for RNA design using deep reinforcement learning.
    """

    def __init__(self, dot_brackets, env_config):
        """TODO
        Initialize an environemnt.

        Args:
            env_config: The configuration of the environment.
        """
        self._env_config = env_config
        # print("dot brackets", dot_brackets)
        if isinstance(dot_brackets[0], str):
            targets = [_Target(dot_bracket, self._env_config) for dot_bracket in dot_brackets]
        else:
            targets = [_Target(dot_bracket, self._env_config, target_id=i) for i, dot_bracket in dot_brackets]
        self._target_gen = _random_epoch_gen(targets)

        self.target = None
        self.design = None
        self.episodes_info = []
        self.predictions = []

    def __str__(self):
        return "RnaDesignEnvironment"

    def seed(self, seed):
        return None

    def reset(self):
        """
        Reset the environment. First function called by runner. Returns first state.

        Returns:
            The first state.
        """
        self.target = next(self._target_gen)
        self.design = _Design(len(self.target))
        return self._get_state()

    def _apply_action(self, action):
        """
        Assign a nucleotide to a site.

        Args:
            action: The action chosen by the agent.
        """
        current_site = self.design.first_unassigned_site
        paired_site = self.target.get_paired_site(current_site)  # None for unpaired sites
        self.design.assign_sites(action, current_site, paired_site)

    def _get_state(self):
        """
        Get a state dependend on the padded encoding of the target structure.

        Returns:
            The next state.
        """
        start = self.design.first_unassigned_site
        return self.target.padded_encoding[
            start : start + 2 * self._env_config.state_radius + 1
        ]

    def _local_improvement(self, folded_design):
        """
        Compute Hamming distance of locally improved candidate solutions.

        Returns:
            The minimum Hamming distance of all imporved candidate solutions.
        """
        differing_sites = _string_difference_indices(
            self.target.dot_bracket, folded_design
        )
        candidates = []
        for mutation in product("AGCU", repeat=len(differing_sites)):
            mutated = self.design.get_mutated(mutation, differing_sites)
            folded_mutated = new_fold(mutated.primary)
            hamming_distance = hamming(folded_mutated, self.target.dot_bracket)
            if hamming_distance == 0:  # For better timing results
                return 0, mutated, folded_mutated
            candidates.append((hamming_distance, mutated, folded_mutated))

        return min(candidates, key=lambda x: x[0])

    def _get_reward(self, terminal):
        """
        Compute the reward after assignment of all nucleotides.

        Args:
            terminal: Bool defining if final timestep is reached yet.

        Returns:
            The reward at the terminal timestep or 0 if not at the terminal timestep.
        """
        if not terminal:
            return 0
        primary = self.design.primary
        folded_design = new_fold(primary)
        hamming_distance = hamming(folded_design, self.target.dot_bracket)
        if 0 < hamming_distance < self._env_config.mutation_threshold:
            hamming_distance, primary, folded_design  = self._local_improvement(folded_design)

        normalized_hamming_distance = hamming_distance / len(self.target)

        if self._env_config.diversity_loss:

            count = Counter(self.predictions)[primary]
            self.predictions.append(primary)
            div_loss = sequence_diversity_loss(count / len(self.predictions))

            loss = normalized_hamming_distance + div_loss

            normalized_distance = min(1.0, loss)



        normalized_distance = normalized_hamming_distance if not self._env_config.diversity_loss else normalized_distance
        # For hparam optimization
        episode_info = EpisodeInfo(
            target_id=self.target.id,
            time=time.time(),
            normalized_hamming_distance=normalized_distance,
            hamming_distance=hamming_distance,
            structure=folded_design,
            sequence=primary,
        )
        self.episodes_info.append(episode_info)

        return (1 - normalized_distance) ** self._env_config.reward_exponent

    def execute(self, actions):
        """
        Execute one interaction of the environment with the agent.

        Args:
            action: Current action of the agent.

        Returns:
            state: The next state for the agent.
            terminal: The signal for end of an episode.
            reward: The reward if at terminal timestep, else 0.
        """
        self._apply_action(actions)

        terminal = self.design.first_unassigned_site is None
        state = None if terminal else self._get_state()
        reward = self._get_reward(terminal)

        return state, terminal, reward

    def close(self):
        pass

    @property
    def states(self):
        type = "int" if self._env_config.use_embedding else "float"
        if self._env_config.use_conv and not self._env_config.use_embedding:
            return dict(type=type, shape=(1 + 2 * self._env_config.state_radius, 1))
        return dict(type=type, shape=(1 + 2 * self._env_config.state_radius,))

    @property
    def actions(self):
        return dict(type="int", num_actions=4)

if __name__ == '__main__':
    print(new_fold("GGGGGGGGGGGCCCCC"))