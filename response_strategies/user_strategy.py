"""Strategy functions that contestants may modify.

Each function is called by the simulation at a specific decision point. The
``ShippingLineResponseStrategy`` and ``CargoOwnerResponseStrategy`` labels
describe responsibilities, but contestants do not have to keep their logic
strictly separated. When useful, the two response types may be combined. For
example, the logic for ``create_alternative_service_routes`` may instead be
implemented as part of ``adjust_bookings_before_cargo_handling`` so route and
vessel changes are decided together with shipment booking changes.

This version changes exactly ONE of the four decision points relative to
DefaultStrategy -- ``select_vessel_for_berth`` -- and leaves the other three
returning ``None`` (full delegation to DefaultStrategy), so any effect on the
Cumulative Resilience Loss can be attributed to this one change in isolation.
"""


class UserStrategy:
    @staticmethod
    def select_vessel_for_berth(
        maritime_data_context,
        port,
        waiting_vessels,
        available_berths,
        current_time,
        waiting_since_by_vessel=None,
    ):
        """PortResponseStrategy -- normalized Smith's-rule berth priority.

        DefaultStrategy combines four independently-normalized factors
        (40% wait, 30% carried TEU, 20% capacity, -10% workload) with fixed,
        ad-hoc weights. Smith (1956) proved that, on a single server, ordering
        jobs by decreasing weight/processing_time -- not by a separate
        weighted sum of unrelated factors -- minimizes total weighted
        completion time. A berth is exactly a single server: the "weight" of
        a waiting vessel is the TEU it already carries (every one of those
        TEU keeps accumulating transport time while the vessel waits), and
        its "processing time" is the cargo-handling duration it will occupy
        the berth with, computed with the same formula
        ``berth_handling_cargo.py:_get_duration`` uses:
        ``(discharging_teu + loading_teu) / (quay_crane_count * 45)``, with
        ``quay_crane_count = max(1, int(loa / 55))``.

        The one thing an earlier version of this file got wrong: it used that
        ratio raw and unbounded, so a vessel with ~0 handling workload at this
        stop (large carried TEU, nothing to load/discharge here) produced an
        arbitrarily huge score that could dominate every other vessel in the
        queue regardless of how long they had been waiting. This version
        keeps DefaultStrategy's own safeguard -- min-max normalization to
        [0, 1] within the current waiting group -- applied to the Smith ratio
        itself, then blends it with a normalized waiting-time term for
        fairness, exactly the way DefaultStrategy blends its own factors.
        """
        if not waiting_vessels:
            return None
        waiting_since_by_vessel = waiting_since_by_vessel or {}

        def waiting_hours(vessel):
            waiting_since = waiting_since_by_vessel.get(vessel, current_time)
            return max(0.0, (current_time - waiting_since).total_seconds() / 3600.0)

        def carried_teu(vessel):
            return sum(
                getattr(shipment, "teu_size", 0) or 0
                for shipment in getattr(vessel, "carried_shipments", [])
            )

        def quay_crane_count(vessel):
            vessel_class = getattr(vessel, "vessel_class", None)
            loa = getattr(vessel_class, "loa", 0) or 0
            return max(1, int(loa / 55))

        def handling_workload(vessel):
            try:
                discharging_teu = sum(
                    getattr(shipment, "teu_size", 0) or 0
                    for shipment in vessel.get_discharging_shipments_at_current_segment()
                )
                loading_teu = sum(
                    getattr(shipment, "teu_size", 0) or 0
                    for shipment in vessel.get_loading_shipments_at_next_segment()
                )
                return discharging_teu + loading_teu
            except (AttributeError, TypeError, ValueError):
                return 0.0

        def smith_ratio(vessel):
            estimated_service_hours = max(
                handling_workload(vessel) / (quay_crane_count(vessel) * 45.0),
                0.1,
            )
            return carried_teu(vessel) / estimated_service_hours

        def normalize(values):
            minimum = min(values)
            maximum = max(values)
            if maximum == minimum:
                return [0.0] * len(values)
            span = maximum - minimum
            return [(value - minimum) / span for value in values]

        smith_scores = normalize([smith_ratio(vessel) for vessel in waiting_vessels])
        waiting_scores = normalize([waiting_hours(vessel) for vessel in waiting_vessels])

        priority_scores = [
            0.7 * smith_score + 0.3 * waiting_score
            for smith_score, waiting_score in zip(smith_scores, waiting_scores)
        ]

        return max(
            enumerate(waiting_vessels),
            key=lambda item: (priority_scores[item[0]], -item[0]),
        )[1]

    @staticmethod
    def create_alternative_service_routes(context, now, vessel=None):
        """ShippingLineResponseStrategy.

        Optionally create disruption-avoiding routes from existing legs and
        reserve existing vessels for those routes.

        A newly created service route must be composed only of ``Leg`` objects
        that already exist in ``context.legs``. This strategy must not create
        new legs. Vessels assigned to a new route must be transferred from
        existing service routes; this strategy must not create new vessels, and
        the total number of vessels in ``context.vessels`` must remain unchanged.

        The simulation validates these constraints after every call, including
        calls that return ``None``. Returning ``None`` means the method did not
        handle the decision and must leave the context unchanged so the default
        implementation can run safely.

        Return ``None`` to use the default implementation. This logic may
        instead be incorporated into ``adjust_bookings_before_cargo_handling``
        when a combined shipping-line and cargo-owner decision is preferred.
        """
        return None

    @staticmethod
    def assign_associated_bookings(context, now, shipment):
        """CargoOwnerResponseStrategy.

        Assign the initial booking chain for a newly generated shipment.

        A custom strategy should create the required ``Booking`` objects,
        populate ``shipment.associated_bookings`` in sequence order, register
        each booking in its service route's ``associated_bookings`` collection,
        and set ``shipment.current_booking_index``.

        Parameters
        ----------
        context:
            The complete maritime data context. The shipment's origin and
            destination are available through ``shipment.demand``.
        now:
            Current simulation time as a ``datetime``.
        shipment:
            The ``Shipment`` that needs its initial bookings.

        Returns
        -------
        bool
            Return ``True`` when a valid booking chain has been assigned.
            Return ``False`` when no booking can currently be assigned; the
            simulation may keep the shipment waiting and retry later.
        """
        return None

    @staticmethod
    def adjust_bookings_before_cargo_handling(context, now, vessel):
        """CargoOwnerResponseStrategy.

        Replan carried shipments before a vessel starts cargo handling.

        This is the only in-transit booking-replanning decision point. It is
        called after the vessel reaches a port and before loading and discharging
        decisions are processed. A custom strategy may inspect
        ``vessel.carried_shipments`` and modify each affected shipment's booking
        chain and current booking index.

        Parameters
        ----------
        context:
            The complete maritime data context, including active
            ``disruption_plans`` and available ``service_routes``.
        now:
            Current simulation time as a ``datetime``.
        vessel:
            The arriving ``Vessel``. Its current location is represented by
            ``vessel.current_segment`` and its onboard shipments by
            ``vessel.carried_shipments``.

        Returns
        -------
        bool
            Return ``True`` after updating the affected booking chains.
        """
        return None
