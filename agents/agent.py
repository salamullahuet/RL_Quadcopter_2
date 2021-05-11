import numpy as np
from tasks.task import Task
import tensorflow as tf

from memory import RingBuffer as ReplayBuffer

from tensorflow.contrib.keras import layers, models, optimizers
from tensorflow.contrib.keras import backend as K
from tensorflow.contrib.keras import activations
from tensorflow.contrib.keras import regularizers
from tensorflow.contrib.keras import initializers

class DDPG():
    """Reinforcement Learning agent that learns using DDPG."""
    def __init__(self, task, gym=False):
        self.task = task
        if gym:
            self.state_size = np.prod(task.observation_space.shape)
            self.action_size = np.prod(task.action_space.shape)
            self.action_low = task.action_space.low
            self.action_high = task.action_space.high
        else:
            self.state_size = task.state_size
            self.action_size = task.action_size
            self.action_low = task.action_low
            self.action_high = task.action_high

        # Actor (Policy) Model
        self.actor_local = Actor(self.state_size, self.action_size, self.action_low, self.action_high)
        self.actor_target = Actor(self.state_size, self.action_size, self.action_low, self.action_high)

        # Critic (Value) Model
        self.critic_local = Critic(self.state_size, self.action_size)
        self.critic_target = Critic(self.state_size, self.action_size)

        # Initialize target model parameters with local model parameters
        self.critic_target.model.set_weights(self.critic_local.model.get_weights())
        self.actor_target.model.set_weights(self.actor_local.model.get_weights())

        # Replay memory
        self.buffer_size = 100000
        self.batch_size = 128
        self.memory = ReplayBuffer(self.buffer_size, self.batch_size)

        # Algorithm parameters
        self.gamma = 0.95  # discount factor
        self.tau = 1e-3  # for soft update of target parameters

        # Score
        self.score = 0.0

    def reset_episode(self):
        # self.noise.reset()
        state = self.task.reset()
        self.last_state = state
        self.score = 0.0
        # self.noise.sigma = max(0.001, self.noise.sigma*0.99)
        return state

    def step(self, action, reward, next_state, done):
         # Save experience / reward
        self.memory.add(self.last_state, action, reward, next_state, done)

        # Learn, if enough samples are available in memory
        if len(self.memory) > self.batch_size:
            experiences = self.memory.sample()
            self.learn(experiences)

        # Roll over last state and action
        self.last_state = next_state

        # Add in step reward to episode score
        self.score += reward

    def add_to_memory(self, last_state, action, reward, next_state, done):
        self.memory.add(last_state, action, reward, next_state, done)

    def act(self, states):
        """Returns actions for given state(s) as per current policy with added noise for exploration."""
        # normalize state
        if hasattr(self.memory, 'state_norm') and self.memory.state_norm is not None:
            states = self.memory.state_norm.normalize(states)

        state = np.reshape(states, [-1, self.state_size])

        action = self.actor_local.model.predict(state)[0]
        return action

    def learn(self, experiences):
        """Update policy and value parameters using given batch of experience tuples."""

        # Unpack experiences
        states, actions, rewards, next_states, dones = experiences

        # Get predicted next-state actions and Q values from target models
        #     Q_targets_next = critic_target(next_state, actor_target(next_state))
        actions_next = self.actor_target.model.predict_on_batch(next_states)
        Q_targets_next = self.critic_target.model.predict_on_batch([next_states, actions_next])

        # Compute Q targets for current states and train critic model (local)
        Q_targets = rewards + self.gamma * Q_targets_next * (1 - dones)

        # Train critic model (local)
        self.critic_local.model.train_on_batch(x=[states, actions], y=Q_targets)

        # Train actor model (local)
        action_gradients = np.reshape(self.critic_local.get_action_gradients([states, actions, 0]),
                                      (-1, self.action_size))
        self.actor_local.train_fn([states, action_gradients, 1])  # custom training function

        # Soft-update target models
        self.soft_update(self.critic_local.model, self.critic_target.model)
        self.soft_update(self.actor_local.model, self.actor_target.model)

    def soft_update(self, local_model, target_model):
        """Soft update model parameters."""
        local_weights = np.array(local_model.get_weights())
        target_weights = np.array(target_model.get_weights())

        assert len(local_weights) == len(target_weights), "Local and target model parameters must have the same size"

        new_weights = self.tau * local_weights + (1 - self.tau) * target_weights
        target_model.set_weights(new_weights)


class Actor:
    """Actor (Policy) Model."""

    def __init__(self, state_size, action_size, action_low, action_high):
        """Initialize parameters and build model.

        Params
        ======
            state_size (int): Dimension of each state
            action_size (int): Dimension of each action
            action_low (array): Min value of each action dimension
            action_high (array): Max value of each action dimension
        """
        self.state_size = state_size
        self.action_size = action_size
        self.action_low = action_low
        self.action_high = action_high
        self.action_range = self.action_high - self.action_low

        # Initialize any other variables here

        self.build_model()

    def build_model(self):
        kernel_l2_reg = 1e-5

        """Build an actor (policy) network that maps states -> actions."""
        # Define input layer (states)
        states = layers.Input(shape=(self.state_size,), name='states')

        # size_repeat = 30
        # block_size = size_repeat*self.state_size
        # print("Actor block size = {}".format(block_size))
        #
        # net = layers.concatenate([states]*size_repeat)
        # # net = layers.Dense(block_size,
        # #                    # kernel_initializer=initializers.RandomNormal(mean=1.0, stddev=0.1),
        # #                    #  bias_initializer=initializers.RandomNormal(mean=0.0, stddev=0.01),
        # #                    activation=None,
        # #                    use_bias=False)(states)
        # net = layers.BatchNormalization()(net)
        # net = layers.Dropout(0.2)(net)
        # # net = layers.LeakyReLU(1e-2)(net)
        #
        # for _ in range(5):
        #     net = res_block(net, block_size)

        # Add hidden layers
        net = layers.Dense(units=300, kernel_regularizer=regularizers.l2(kernel_l2_reg))(states)
        net = layers.BatchNormalization()(net)
        net = layers.LeakyReLU(1e-2)(net)

        net = layers.Dense(units=400, kernel_regularizer=regularizers.l2(kernel_l2_reg))(net)
        net = layers.BatchNormalization()(net)
        net = layers.LeakyReLU(1e-2)(net)

        net = layers.Dense(units=200, kernel_regularizer=regularizers.l2(kernel_l2_reg))(net)
        net = layers.BatchNormalization()(net)
        net = layers.LeakyReLU(1e-2)(net)


        # Try different layer sizes, activations, add batch normalization, regularizers, etc.

        # # Add final output layer with sigmoid activation
        # raw_actions = layers.Dense(units=self.action_size,
        #                            activation='sigmoid',
        #                            # kernel_regularizer=regularizers.l2(kernel_l2_reg),
        #                            kernel_initializer=initializers.RandomUniform(minval=-3e-3, maxval=3e-3),
        #                            # bias_initializer=initializers.RandomUniform(minval=-3e-3, maxval=3e-3),
        #                            name='raw_actions')(net)
        #
        # # Scale [0, 1] output for each action dimension to proper range
        # actions = layers.Lambda(lambda x: (x * self.action_range) + self.action_low, name='actions')(raw_actions)

        actions = layers.Dense(units=self.action_size,
                               activation='tanh',
                               kernel_regularizer=regularizers.l2(kernel_l2_reg),
                               kernel_initializer=initializers.RandomUniform(minval=-3e-3, maxval=3e-3),
                               name='actions'
                               )(net)

        # Create Keras model
        self.model = models.Model(inputs=states, outputs=actions)

        # Define loss function using action value (Q value) gradients
        action_gradients = layers.Input(shape=(self.action_size,))
        loss = K.mean(-action_gradients * actions)

        # Incorporate any additional losses here (e.g. from regularizers)

        # Define optimizer and training function
        optimizer = optimizers.Adam(lr=1e-4)

        updates_op = optimizer.get_updates(params=self.model.trainable_weights, loss=loss)
        self.train_fn = K.function(
            inputs=[self.model.input, action_gradients, K.learning_phase()],
            outputs=[],
            updates=updates_op)


class Critic:
    """Critic (Value) Model."""

    def __init__(self, state_size, action_size):
        """Initialize parameters and build model.

        Params
        ======
            state_size (int): Dimension of each state
            action_size (int): Dimension of each action
        """
        self.state_size = state_size
        self.action_size = action_size

        # Initialize any other variables here

        self.build_model()

    def build_model(self):
        kernel_l2_reg = 1e-5

        # Dense Options
        # units = 200,
        # activation='relu',
        # activation = None,
        # activity_regularizer=regularizers.l2(0.01),
        # kernel_regularizer=regularizers.l2(kernel_l2_reg),
        # bias_initializer=initializers.Constant(1e-2),
        # use_bias = True
        # use_bias=False

        """Build a critic (value) network that maps (state, action) pairs -> Q-values."""
        # Define input layers
        states = layers.Input(shape=(self.state_size,), name='states')
        actions = layers.Input(shape=(self.action_size,), name='actions')

        # size_repeat = 30
        # state_size = size_repeat*self.state_size
        # action_size = size_repeat*self.action_size
        # block_size = size_repeat*self.state_size + size_repeat*self.action_size
        # print("Critic block size = {}".format(block_size))
        #
        # net_states = layers.concatenate(size_repeat * [states])
        # net_states = layers.BatchNormalization()(net_states)
        # net_states = layers.Dropout(0.2)(net_states)
        #
        # net_actions = layers.concatenate(size_repeat * [actions])
        # net_actions = layers.BatchNormalization()(net_actions)
        # net_actions = layers.Dropout(0.2)(net_actions)
        #
        # # State pathway
        # for _ in range(3):
        #     net_states = res_block(net_states, state_size)
        #
        # # Action pathway
        # for _ in range(2):
        #     net_actions = res_block(net_actions, action_size)
        #
        # # Merge state and action pathways
        # net = layers.concatenate([net_states, net_actions])
        #
        # # Final blocks
        # for _ in range(3):
        #     net = res_block(net, block_size)


        # Add hidden layer(s) for state pathway
        net_states = layers.Dense(units=300, kernel_regularizer=regularizers.l2(kernel_l2_reg))(states)
        net_states = layers.BatchNormalization()(net_states)
        net_states = layers.LeakyReLU(1e-2)(net_states)

        net_states = layers.Dense(units=400, kernel_regularizer=regularizers.l2(kernel_l2_reg))(net_states)
        net_states = layers.BatchNormalization()(net_states)
        net_states = layers.LeakyReLU(1e-2)(net_states)

        # Add hidden layer(s) for action pathway
        net_actions = layers.Dense(units=400, kernel_regularizer=regularizers.l2(kernel_l2_reg))(actions)
        net_actions = layers.BatchNormalization()(net_actions)
        net_actions = layers.LeakyReLU(1e-2)(net_actions)

        # Merge state and action pathways
        net = layers.add([net_states, net_actions])

        net = layers.Dense(units=200, kernel_regularizer=regularizers.l2(kernel_l2_reg))(net)
        net = layers.BatchNormalization()(net)
        net = layers.LeakyReLU(1e-2)(net)

        # Add final output layer to prduce action values (Q values)
        Q_values = layers.Dense(units=1,
                                activation=None,
                                kernel_regularizer=regularizers.l2(kernel_l2_reg),
                                kernel_initializer=initializers.RandomUniform(minval=-5e-3, maxval=5e-3),
                                # bias_initializer=initializers.RandomUniform(minval=-3e-3, maxval=3e-3),
                                name='q_values')(net)

        # Create Keras model
        self.model = models.Model(inputs=[states, actions], outputs=Q_values)

        # Define optimizer and compile model for training with built-in loss function
        optimizer = optimizers.Adam(lr=1e-2)

        self.model.compile(optimizer=optimizer, loss='mse')

        # Compute action gradients (derivative of Q values w.r.t. to actions)
        action_gradients = K.gradients(Q_values, actions)

        # Define an additional function to fetch action gradients (to be used by actor model)
        self.get_action_gradients = K.function(
            inputs=[*self.model.input, K.learning_phase()],
            outputs=action_gradients)


def res_block(inputs, size):
    kernel_l2_reg = 1e-3
    net = layers.Dense(size,
                       activation=None,
                       kernel_regularizer=regularizers.l2(kernel_l2_reg),
                       kernel_initializer=initializers.RandomUniform(minval=-5e-3, maxval=5e-3)
                       )(inputs)
    net = layers.BatchNormalization()(net)
    net = layers.LeakyReLU(1e-2)(net)

    net = layers.Dense(size,
                       activation=None,
                       kernel_regularizer=regularizers.l2(kernel_l2_reg),
                       kernel_initializer=initializers.RandomUniform(minval=-5e-3, maxval=5e-3)
                       )(net)
    net = layers.BatchNormalization()(net)
    net = layers.LeakyReLU(1e-2)(net)
    net = layers.add([inputs, net])
    return net


