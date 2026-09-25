"""Registration API for WebApp actions and ImFusion algorithms."""

import inspect
import logging
from typing import (
    Any,
    Callable,
    List,
    Literal,
    Optional,
    Sequence,
    TypeVar,
    overload,
)

from .action_registry import ActionRegistry
from .algorithm_registry import AlgorithmRegistry
from .input_spec import InputSpec
from .parameter_spec import ParameterDefinition

logger = logging.getLogger(__name__)

_CallableT = TypeVar("_CallableT", bound=Callable[..., Any])
_AlgorithmClassT = TypeVar("_AlgorithmClassT", bound=type)


class OperationRegistrationMixin:
    """Provide the public operation-registration API to ``ImFusionWebApp``."""

    action_registry: ActionRegistry
    algorithm_registry: AlgorithmRegistry

    @overload
    def register(
        self,
        name: str,
        target: _AlgorithmClassT,
        *,
        inputs: Optional[List[InputSpec]] = ...,
        result_input: Optional[str] = ...,
        placement: Optional[Literal["sidebar", "header"]] = ...,
    ) -> _AlgorithmClassT: ...

    @overload
    def register(
        self,
        name: str,
        target: _CallableT,
        *,
        inputs: Optional[List[InputSpec]] = ...,
        result_input: Optional[str] = ...,
        parameters: Optional[Sequence[ParameterDefinition]] = ...,
    ) -> _CallableT: ...

    @overload
    def register(
        self,
        name: str,
        *,
        inputs: Optional[List[InputSpec]] = ...,
        result_input: Optional[str] = ...,
        parameters: Optional[Sequence[ParameterDefinition]] = ...,
    ) -> Callable[[_CallableT], _CallableT]: ...

    @overload
    def register(
        self,
        name: str,
        *,
        inputs: Optional[List[InputSpec]] = ...,
        result_input: Optional[str] = ...,
        placement: Literal["sidebar", "header"],
    ) -> Callable[[_AlgorithmClassT], _AlgorithmClassT]: ...

    @overload
    def register(
        self,
        name: str,
        *,
        algorithm: str,
        inputs: Optional[List[InputSpec]] = ...,
        result_input: Optional[str] = ...,
        placement: Optional[Literal["sidebar", "header"]] = ...,
    ) -> str: ...

    @overload
    def register(
        self,
        name: str,
        *,
        algorithm: _AlgorithmClassT,
        inputs: Optional[List[InputSpec]] = ...,
        result_input: Optional[str] = ...,
        placement: Optional[Literal["sidebar", "header"]] = ...,
    ) -> _AlgorithmClassT: ...

    def register(
        self,
        name: str,
        target: Optional[Callable[..., Any]] = None,
        *,
        algorithm: Optional[object] = None,
        inputs: Optional[List[InputSpec]] = None,
        result_input: Optional[str] = None,
        parameters: Optional[Sequence[ParameterDefinition]] = None,
        placement: Optional[Literal["sidebar", "header"]] = None,
    ) -> Any:
        """Register a web action or expose an ImFusion algorithm."""

        def decorator(target):
            if inspect.isclass(target):
                algorithm_id = getattr(target, "id", None)
                if not isinstance(algorithm_id, str):
                    raise TypeError(
                        "Action classes must first be registered with "
                        "@imfusion.algorithm.register; use a function for "
                        "WebApp-only actions"
                    )
                if parameters is not None:
                    raise ValueError(
                        "SDK algorithms expose parameters through Properties"
                    )
                self._register_algorithm(
                    name,
                    algorithm_id,
                    inputs=inputs,
                    result_input=result_input,
                    placement=placement or "sidebar",
                )
            else:
                if placement is not None:
                    raise ValueError("placement is only supported for algorithms")
                self.action_registry.register(
                    name,
                    target,
                    inputs,
                    result_input,
                    parameters,
                )
                logger.info("Registered action: %s", name)
            return target

        if algorithm is not None:
            if target is not None:
                raise TypeError("Pass either target or algorithm, not both")
            if parameters is not None:
                raise ValueError("SDK algorithms expose parameters through Properties")
            algorithm_id = (
                algorithm
                if isinstance(algorithm, str)
                else getattr(algorithm, "id", None)
            )
            if not isinstance(algorithm_id, str):
                raise TypeError(
                    "algorithm must be an algorithm ID or an "
                    "@imfusion.algorithm.register class"
                )
            self._register_algorithm(
                name,
                algorithm_id,
                inputs=inputs,
                result_input=result_input,
                placement=placement or "sidebar",
            )
            return algorithm
        return decorator(target) if target is not None else decorator

    @staticmethod
    def _validate_placement(placement: str) -> None:
        if placement not in {"sidebar", "header"}:
            raise ValueError("placement must be either 'sidebar' or 'header'")

    def _register_algorithm(
        self,
        title: str,
        algorithm_id: str,
        *,
        inputs: Optional[List[InputSpec]] = None,
        result_input: Optional[str] = None,
        placement: Literal["sidebar", "header"] = "sidebar",
    ) -> None:
        """Expose one SDK-registered algorithm as a dedicated web panel."""
        self._validate_placement(placement)
        self.algorithm_registry.register_controller(
            algorithm_id,
            title=title,
            inputs=inputs,
            result_input=result_input,
            placement=placement,
        )
        logger.info("Registered algorithm panel: %s (%s)", title, algorithm_id)
