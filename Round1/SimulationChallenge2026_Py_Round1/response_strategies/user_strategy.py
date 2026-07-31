"""Strategy functions that contestants may modify.

Each function is called by the simulation at a specific decision point. The
``ShippingLineResponseStrategy`` and ``CargoOwnerResponseStrategy`` labels
describe responsibilities, but contestants do not have to keep their logic
strictly separated. When useful, the two response types may be combined. For
example, the logic for ``create_alternative_service_routes`` may instead be
implemented as part of ``adjust_bookings_before_cargo_handling`` so route and
vessel changes are decided together with shipment booking changes.
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
        """PortResponseStrategy.

        Select the next vessel to receive a berth at a congested port.

        This function is called when the number of waiting vessels reaches the
        configured port-congestion threshold. It is not called when the normal
        first-in-first-out selection is sufficient.

        Parameters
        ----------
        maritime_data_context:
            The complete maritime data context.
        port:
            The ``Port`` where a berth is being assigned.
        waiting_vessels:
            Ordered list of vessels currently waiting at ``port``. The selected
            vessel must be an object from this list.
        available_berths:
            List of currently available berth objects at ``port``. This can be
            used to inspect available capacity, but this function selects a
            vessel rather than a berth.
        current_time:
            Current simulation time as a ``datetime``.
        waiting_since_by_vessel:
            Mapping ``{vessel: waiting_start_time}``. It may be ``None``.
            Use it to calculate how long each vessel has waited.

        Returns
        -------
        Vessel
            Return exactly one vessel contained in ``waiting_vessels``.
            Returning another object raises a ``ValueError``.
        """
        return None

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
