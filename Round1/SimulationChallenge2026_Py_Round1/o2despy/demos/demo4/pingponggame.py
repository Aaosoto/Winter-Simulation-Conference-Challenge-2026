from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from o2des.core import Sandbox
from o2des.utils import LogUtils

from .pingpongplayer import PingPongPlayer


@dataclass
class Statics:
    player1: PingPongPlayer.Statics
    player2: PingPongPlayer.Statics


class PingPongGame(Sandbox):

    Statics = Statics

    def __init__(
        self,
        config: Statics,
        seed=0,
    ) -> None:
        super().__init__(seed=seed)
        # Statics
        self._config: Statics = config
        # Dynamics
        self.player1: PingPongPlayer = self.add_child(
            PingPongPlayer(self._config.player1, seed))
        self.player2: PingPongPlayer = self.add_child(
            PingPongPlayer(self._config.player2, seed))
        # Events
        self.player1.on_send += self.player2.receive
        self.player2.on_send += self.player1.receive
        self.schedule(self.player1.receive)

    @property
    def config(self) -> Statics:
        return self._config


def run_sim() -> None:
    LogUtils.get_logger().reset()
    config = PingPongGame.Statics(
        player1=PingPongPlayer.Statics(
            index=0,
            delay_time_expected=2,
            delay_time_CV=0.1,
        ),
        player2=PingPongPlayer.Statics(
            index=1,
            delay_time_expected=1.8,
            delay_time_CV=0.15,
        ),
    )
    sim = PingPongGame(config, seed=0)
    sim.run(event_count=10)