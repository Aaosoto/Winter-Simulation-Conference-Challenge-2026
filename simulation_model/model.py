"""
Model - Main simulation orchestration for WSC Simulation Challenge 2026.

Wires together all generators, activities, and signal handlers to create
the complete maritime shipping simulation with event flow and signal coordination.
"""

from __future__ import annotations

from o2des.core import Sandbox

from maritime_data_context import MaritimeDataContext

from .shipment_generator import ShipmentGenerator
from .vessel_generator import VesselGenerator
from .berth_generator import BerthGenerator
from .shipment_waiting_for_loading_at_origin_port import ShipmentWaitingForLoadingAtOriginPort
from .shipment_waiting_for_loading_at_transshipment_port import ShipmentWaitingForLoadingAtTransshipmentPort
from .shipment_being_transported import ShipmentBeingTransported
from .vessel_awaiting_instructions import VesselAwaitingInstructions
from .vessel_sailing import VesselSailing
from .vessel_queuing_for_berth import VesselQueuingForBerth
from .vessel_being_served import VesselBeingServed
from .berth_idle import BerthIdle
from .berth_berthing import BerthBerthing
from .berth_handling_cargo import BerthHandlingCargo
from .disruption_manager import DisruptionManager


class Model(Sandbox):
    """
    Main simulation model orchestrating all components.

    The model contains:
    - 3 Generators: Shipment, Vessel, Berth
    - 10 Activities: Shipment (3), Vessel (4), Berth (3)
    - 17 Event wires (ConnectTo) for entity flow
    - 7 Signal wires (on_finish/on_start -> Signal) for cross-component coordination
    """

    def __init__(
        self,
        data_context: MaritimeDataContext,
        seed: int = 0
    ):
        """
        Initialize the simulation model.

        Parameters
        ----------
        data_context : MaritimeDataContext
            The maritime domain data for this simulation scenario.
        seed : int
            Random seed for the root sandbox.
        """
        super().__init__(seed=seed, uid="Model")
        self.data_context = data_context
        self.simulation_start_time = self.clock_time
        self.disruption_manager = None

        # --- Generators ---
        self.shipment_generator = self._add_child(
            ShipmentGenerator(data_context, seed=self._default_rs.next())
        )
        self.vessel_generator = self._add_child(
            VesselGenerator(data_context, seed=self._default_rs.next())
        )
        self.berth_generator = self._add_child(
            BerthGenerator(data_context, seed=self._default_rs.next())
        )

        # --- Activities ---
        # Pass data_context to activities that maintain per-key HourCounters
        # so that the counters are eagerly created with _creation_time = sim
        # start (matching the reference behavior's AddHourCounter() with _initialTime =
        # DateTime.MinValue). Without this, lazy per-key counters would be
        # created at first observation, biasing the time-weighted average.
        self.shipment_waiting_for_loading_at_origin_port = self._add_child(
            ShipmentWaitingForLoadingAtOriginPort(data_context, seed=self._default_rs.next())
        )
        self.shipment_waiting_for_loading_at_transshipment_port = self._add_child(
            ShipmentWaitingForLoadingAtTransshipmentPort(data_context, seed=self._default_rs.next())
        )
        self.shipment_being_transported = self._add_child(
            ShipmentBeingTransported(data_context, seed=self._default_rs.next())
        )
        self.vessel_awaiting_instructions = self._add_child(
            VesselAwaitingInstructions(seed=self._default_rs.next())
        )
        self.vessel_sailing = self._add_child(
            VesselSailing(data_context, seed=self._default_rs.next())
        )
        self.vessel_queuing_for_berth = self._add_child(
            VesselQueuingForBerth(data_context, seed=self._default_rs.next())
        )
        self.vessel_being_served = self._add_child(
            VesselBeingServed(
                seed=self._default_rs.next(),
                data_context=data_context,
            )
        )
        self.berth_idle = self._add_child(
            BerthIdle(data_context, seed=self._default_rs.next())
        )
        self.berth_berthing = self._add_child(
            BerthBerthing(seed=self._default_rs.next())
        )
        self.berth_handling_cargo = self._add_child(
            BerthHandlingCargo(seed=self._default_rs.next())
        )

        # =========================================================
        # Event Wiring (Core Entity Flow)
        # =========================================================

        # --- Shipment flow ---
        # ShipmentGenerator -> ShipmentWaitingForLoadingAtOriginPort
        self._connect_generator_flow(
            self.shipment_generator,
            self.shipment_waiting_for_loading_at_origin_port
        )

        # ShipmentWaitingForLoadingAtOriginPort -> ShipmentBeingTransported
        self._connect_activity_flow(
            self.shipment_waiting_for_loading_at_origin_port,
            self.shipment_being_transported
        )

        # ShipmentBeingTransported -> ShipmentWaitingForLoadingAtTransshipmentPort (if not at last booking)
        self._connect_conditional_event_flow(
            self.shipment_being_transported,
            self.shipment_waiting_for_loading_at_transshipment_port,
            lambda s: not s.is_at_last_booking()
        )

        # ShipmentBeingTransported terminates (if at last booking)
        self._connect_termination(
            self.shipment_being_transported,
            lambda s: s.is_at_last_booking(),
            self._record_shipment_completion,
        )

        # ShipmentWaitingForLoadingAtTransshipmentPort -> ShipmentBeingTransported
        self._connect_activity_flow(
            self.shipment_waiting_for_loading_at_transshipment_port,
            self.shipment_being_transported
        )

        # --- Vessel flow ---
        # VesselGenerator -> VesselAwaitingInstructions
        self._connect_generator_flow(
            self.vessel_generator,
            self.vessel_awaiting_instructions
        )

        # VesselAwaitingInstructions -> VesselSailing
        self._connect_activity_flow(
            self.vessel_awaiting_instructions,
            self.vessel_sailing
        )

        # VesselSailing -> VesselQueuingForBerth
        self._connect_activity_flow(
            self.vessel_sailing,
            self.vessel_queuing_for_berth
        )

        # VesselQueuingForBerth -> VesselBeingServed
        # Reference Model.cs line 89: VesselQueuingForBerth.ConnectTo(VesselBeingServed)
        # ConnectTo does two things:
        #   1. on_finish -> next.RequestStart (forward entity)
        #   2. next.on_start -> this.depart (departure trigger)
        # VBS.signal_start(Shipment) overrides inherited signal_start(Vessel), so
        # calling signal_start(vessel) dispatches to ActivityHandler.signal_start(Vessel)
        # which adds vessel to r_loads_requested_start of VBS (correct behavior).
        self.vessel_queuing_for_berth.on_finish.add(
            lambda vessel: self.vessel_being_served.signal_start(vessel)
        )
        self.vessel_being_served.on_start.add(
            lambda vessel: self.vessel_queuing_for_berth.depart(vessel)
        )

        # VesselBeingServed -> VesselSailing (unconditional loop)
        self._connect_activity_flow(
            self.vessel_being_served,
            self.vessel_sailing
        )

        # --- Berth flow ---
        # BerthGenerator -> BerthIdle
        self._connect_generator_flow(
            self.berth_generator,
            self.berth_idle
        )

        # BerthIdle -> BerthBerthing
        self._connect_activity_flow(
            self.berth_idle,
            self.berth_berthing
        )

        # BerthBerthing -> BerthHandlingCargo
        self._connect_activity_flow(
            self.berth_berthing,
            self.berth_handling_cargo
        )

        # BerthHandlingCargo -> BerthIdle (unconditional loop)
        self._connect_activity_flow(
            self.berth_handling_cargo,
            self.berth_idle
        )

        # =========================================================
        # Signal Wiring (Cross-Flow Coordination)
        # =========================================================

        # Shipment readiness at port enables vessel service
        # Reference Model.cs line 104-105:
        #   SWfL.AO.on_finish.Add(VesselBeingServed.signal_start)
        #   SWfL.TP.on_finish.Add(VesselBeingServed.signal_start)
        # Python: use explicit signal_start_shipment to avoid polymorphic dispatch issues
        self.shipment_waiting_for_loading_at_origin_port.on_finish.add(
            lambda shipment: self.vessel_being_served.signal_start_shipment(shipment)
        )
        self.shipment_waiting_for_loading_at_transshipment_port.on_finish.add(
            lambda shipment: self.vessel_being_served.signal_start_shipment(shipment)
        )

        # Vessel service drives shipment transport state transition
        # Reference Model.cs line 108-109:
        #   VesselBeingServed.on_start.Add(ShipmentBeingTransported.signal_start)
        #   VesselBeingServed.on_finish.Add(ShipmentBeingTransported.signal_finish)
        self.vessel_being_served.on_start.add(
            lambda vessel: self.shipment_being_transported.signal_start(vessel)
        )
        self.vessel_being_served.on_finish.add(
            lambda vessel: self.shipment_being_transported.signal_finish(vessel)
        )

        # Vessel queueing and berth assignment coordination
        # VesselQueuingForBerth.on_start fires when vessel arrives at port (ready for berth)
        self.vessel_queuing_for_berth.on_start.add(
            lambda vessel: self.berth_idle.signal_finish(vessel)
        )
        # BerthBerthing.on_start: berth starting berthing -> signal vessel queuing that berth is engaged
        self.berth_berthing.on_start.add(
            lambda berth: self.vessel_queuing_for_berth.signal_finish(berth)
        )

        # Give VesselQueuingForBerth a back-reference to BerthIdle
        # (needed so it can return unused berths to idle)
        self.vessel_queuing_for_berth.berth_idle = self.berth_idle

        # Vessel service and berth cargo handling coordination
        self.vessel_being_served.on_start.add(
            lambda vessel: self.berth_handling_cargo.signal_start(vessel)
        )
        # BerthHandlingCargo.on_finish: cargo done -> vessel departs
        # Note: BerthIdle.signal_start is already wired via
        # _connect_event_flow(BerthHandlingCargo -> BerthIdle) Event Flow,
        # so no need to trigger it again here.
        self.berth_handling_cargo.on_finish.add(
            lambda berth: self.vessel_being_served.signal_finish(berth)
        )

        if self.data_context.disruption_plans:
            self.disruption_manager = self._add_child(
                DisruptionManager(
                    self.data_context,
                    simulation_start=self.simulation_start_time,
                    seed=self._default_rs.next(),
                )
            )

    def get_teu_weighted_average_transport_time_hours(
        self,
        period_start_time,
        period_end_time=None,
    ) -> float:
        """Return backlog-adjusted, TEU-weighted ATT for a reporting period.

        The calculation includes:
        - shipments completed during the reporting period, using their full
          completion time minus generation time; and
        - every shipment still unfinished at the period end, including backlog
          generated in earlier periods, using its age at the period end.

        Shipments completed before the reporting period are excluded.
        """
        period_end_time = period_end_time or self.clock_time
        weighted_hours = 0.0
        total_teu = 0.0
        for demand in self.data_context.demands:
            for shipment in demand.shipments:
                generated_time = shipment.generated_time
                if generated_time is None or generated_time > period_end_time:
                    continue

                completion_time = shipment.completion_time
                completed_in_period = (
                    completion_time is not None
                    and completion_time <= period_end_time
                    and completion_time > period_start_time
                )
                still_backlogged = (
                    completion_time is None
                    or completion_time > period_end_time
                )
                if not completed_in_period and not still_backlogged:
                    continue

                end_time = completion_time if completed_in_period else period_end_time
                duration_hours = max(
                    0.0,
                    (end_time - generated_time).total_seconds() / 3600.0,
                )
                weighted_hours += shipment.teu_size * duration_hours
                total_teu += shipment.teu_size

        return weighted_hours / total_teu if total_teu > 0 else 0.0

    def get_od_flow_status_for_period(
        self,
        period_start_time,
        period_end_time=None,
    ) -> list[dict]:
        """Return period flow and backlog snapshots for each OD demand."""
        period_end_time = period_end_time or self.clock_time
        rows = []

        def is_in_period(timestamp):
            return period_start_time < timestamp <= period_end_time

        for demand in self.data_context.demands:
            generated_teu = 0.0
            completed_teu = 0.0
            cumulative_completed_teu = 0.0
            backlog_teu = 0.0
            completed_weighted_hours = 0.0
            backlog_weighted_hours = 0.0

            for shipment in demand.shipments:
                generated_time = shipment.generated_time
                if generated_time is None or generated_time > period_end_time:
                    continue

                teu = shipment.teu_size
                if is_in_period(generated_time):
                    generated_teu += teu

                completion_time = shipment.completion_time
                if completion_time is not None and completion_time <= period_end_time:
                    cumulative_completed_teu += teu
                    if is_in_period(completion_time):
                        completed_teu += teu
                        completed_weighted_hours += teu * max(
                            0.0,
                            (completion_time - generated_time).total_seconds()
                            / 3600.0,
                        )
                    continue

                backlog_teu += teu
                backlog_weighted_hours += teu * max(
                    0.0,
                    (period_end_time - generated_time).total_seconds() / 3600.0,
                )

            rows.append({
                "origin": demand.origin_port.name,
                "destination": demand.destination_port.name,
                "annual_teus": demand.annual_teus,
                "generated_teu": generated_teu,
                "completed_teu": completed_teu,
                "cumulative_completed_teu": cumulative_completed_teu,
                "backlog_teu": backlog_teu,
                "average_completed_att_hours": (
                    completed_weighted_hours / completed_teu
                    if completed_teu > 0
                    else 0.0
                ),
                "average_backlog_age_hours": (
                    backlog_weighted_hours / backlog_teu
                    if backlog_teu > 0
                    else 0.0
                ),
            })

        return rows

    def _record_shipment_completion(self, shipment) -> None:
        if shipment.completion_time is None:
            shipment.completion_time = self.clock_time

    def _add_child(self, child) -> 'Sandbox':
        """Add a child sandbox to this model."""
        return self.add_child(child)

    def _connect_generator_flow(self, source, target) -> None:
        """
        Connect generator.on_finish -> target.signal_start (unconditional).
        One-way only: generators don't have depart/on_start (no 4-state machine).
        Matches Reference Generator.ConnectTo().
        """
        source.on_finish.add(lambda entity: target.signal_start(entity))

    def _connect_activity_flow(self, source, target) -> None:
        """
        Full two-way ConnectTo matching the reference behavior ActivityHandler.ConnectTo().

        1. source.on_finish -> target.signal_start (forward entity)
        2. target.on_start -> source.depart (departure trigger)

        This ensures entities held in f_loads_finished of source are removed
        when target starts them.
        """
        source.on_finish.add(lambda entity: target.signal_start(entity))
        target.on_start.add(lambda entity: source.depart(entity))

    def _connect_conditional_event_flow(self, source, target, predicate) -> None:
        """
        Two-way ConnectTo with filter, matching the reference behavior ConnectTo(filter).

        1. source.on_finish -> target.signal_start (if predicate(entity) is True)
        2. target.on_start -> source.depart (unconditional, safe guard in depart)
        """
        source.on_finish.add(lambda entity: target.signal_start(entity) if predicate(entity) else None)
        target.on_start.add(lambda entity: source.depart(entity))

    def _connect_termination(self, source, predicate, before_depart=None) -> None:
        """
        Terminal ConnectTo matching the reference behavior Terminate(filter).

        When predicate(entity) is True, calls source.depart(entity)
        so the entity exits the process flow cleanly.
        """
        def terminate(entity):
            if not predicate(entity):
                return
            if before_depart is not None:
                before_depart(entity)
            source.depart(entity)

        source.on_finish.add(terminate)
