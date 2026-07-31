from __future__ import annotations

import math


class Pointer:
    """
    A 2D pointer with position, rotation angle, and flip state.

    Represents a point in 2D space with transformation capabilities including
    translation, rotation, and mirroring.

    Examples
    --------
    >>> p1 = Pointer(1, 2, 45, False)
    >>> p2 = Pointer(3, 4, 90, False)
    >>> result = p1 * p2  # Compose transformations
    >>> relative = p1 / p2  # Get relative transformation
    """

    def __init__(
        self,
        x: float = 0.0,
        y: float = 0.0,
        angle: float = 0.0,
        flipped: bool = False
    ) -> None:
        """
        Initialize a pointer.

        Parameters
        ----------
        x : float, optional
            X coordinate. Defaults to 0.0.
        y : float, optional
            Y coordinate. Defaults to 0.0.
        angle : float, optional
            Rotation angle in degrees. Defaults to 0.0.
        flipped : bool, optional
            Whether the pointer is flipped. Defaults to False.
        """
        self._x: float = x
        self._y: float = y
        self._angle: float = angle % 360  # Normalize angle to [0, 360)
        self._flipped: bool = flipped

    @property
    def x(self) -> float:
        """
        X coordinate of the pointer.
        """
        return self._x

    @property
    def y(self) -> float:
        """
        Y coordinate of the pointer.
        """
        return self._y

    @property
    def angle(self) -> float:
        """
        Rotation angle of the pointer in degrees.
        """
        return self._angle

    @property
    def flipped(self) -> bool:
        """
        Whether the pointer is flipped.
        """
        return self._flipped

    def __mul__(self, outer: Pointer) -> Pointer:
        """
        Superposition of two pointers (outer transformation).

        Applies this pointer's transformation in the coordinate system defined
        by the outer pointer.

        Parameters
        ----------
        outer : Pointer
            The outer pointer defining the reference frame.

        Returns
        -------
        Pointer
            A new pointer representing the composed transformation.

        Raises
        ------
        TypeError
            If the operand is not a Pointer.
        """
        if not isinstance(outer, Pointer):
            raise TypeError(f"Operand must be a Pointer, but got {type(outer).__name__}")

        # Convert angle to radians
        # radius = outer.angle / 180 * math.pi
        radius = math.radians(outer.angle)
        # Cache trigonometric values
        cos_a = math.cos(radius)
        sin_a = math.sin(radius)

        # Apply rotation and translation
        new_x = self.x * cos_a - self.y * sin_a + outer.x
        new_y = self.x * sin_a + self.y * cos_a + outer.y
        new_angle = (outer.angle + self.angle) % 360
        new_flipped = outer.flipped ^ self.flipped

        return Pointer(new_x, new_y, new_angle, new_flipped)

    def __truediv__(self, outer: Pointer) -> Pointer:
        """
        Calculate relative transformation (inverse composition).

        Finds the pointer that, when composed with outer, gives this pointer.
        In other words: self = result * outer

        Parameters
        ----------
        outer : Pointer
            The outer pointer.

        Returns
        -------
        Pointer
            The relative pointer.

        Raises
        ------
        TypeError
            If the operand is not a Pointer.
        """
        if not isinstance(outer, Pointer):
            raise TypeError(f"Operand must be a Pointer, got {type(outer).__name__}")

        # Apply inverse transformation in correct order
        # First remove translation, then rotation, then flip
        temp = self * Pointer(-outer.x, -outer.y)
        result = temp * Pointer(angle=-outer.angle, flipped=outer.flipped)
        return result
