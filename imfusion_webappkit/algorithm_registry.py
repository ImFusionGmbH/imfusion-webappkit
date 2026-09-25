"""
Algorithm Registry for managing ImFusion algorithm discovery and execution.
"""

from typing import Dict, List, Any, Literal, Optional
import imfusion
import logging

from .input_spec import InputSpec, normalize_input_specs

logger = logging.getLogger(__name__)


class AlgorithmRegistry:
    """Registry for ImFusion algorithm operations."""

    def __init__(self):
        self._execution_enabled = False  # Allows algorithm execution
        self._generic_panel_enabled = (
            False  # Shows the generic Algorithms dropdown panel
        )
        self._controllers: Dict[str, Dict[str, Any]] = {}  # name -> algorithm info

    def enable(self):
        """Enable the generic algorithm panel and execution support."""
        self._execution_enabled = True
        self._generic_panel_enabled = True
        logger.info("Algorithm support enabled (with generic panel)")

    def is_enabled(self) -> bool:
        """Check if the generic algorithm panel should be shown."""
        return self._generic_panel_enabled

    def is_execution_enabled(self) -> bool:
        """Check if algorithm execution is enabled."""
        return self._execution_enabled

    def register_controller(
        self,
        algorithm_name: str,
        title: Optional[str] = None,
        inputs: Optional[List[InputSpec]] = None,
        result_input: Optional[str] = None,
        placement: Literal["sidebar", "header"] = "sidebar",
    ) -> None:
        """
        Register a dedicated algorithm controller.

        Args:
            algorithm_name: Name of the algorithm (e.g., 'MorphologicalOperations')
            title: Optional custom title for the UI section. Defaults to algorithm_name.

        Raises:
            ValueError: If no algorithm with the given name exists
        """
        # Find the algorithm by name
        available_algos = imfusion.algorithm.list_available()
        matching_algo_id = None

        for algo_id in available_algos:
            display_name = self._get_display_name(algo_id)
            if display_name == algorithm_name or algo_id == algorithm_name:
                matching_algo_id = algo_id
                break

        if matching_algo_id is None:
            raise ValueError(
                f"Algorithm '{algorithm_name}' not found. "
                "Available algorithms can be discovered using "
                "imfusion.algorithm.list_available()."
            )

        input_specs = normalize_input_specs(inputs)
        if not input_specs:
            raise ValueError("Algorithm controllers require at least one input")
        if result_input is not None and result_input not in {
            spec.key for spec in input_specs
        }:
            raise ValueError(f"Unknown result input key: {result_input!r}")

        self._controllers[algorithm_name] = {
            "id": matching_algo_id,
            "name": algorithm_name,
            "title": title if title else algorithm_name,
            "inputs": input_specs,
            "result_input": result_input or input_specs[0].key,
            "placement": placement,
        }

        # Enable execution (but not the generic panel) when controllers are registered
        self._execution_enabled = True
        logger.info(
            f"Registered algorithm controller: {algorithm_name} ({matching_algo_id})"
        )

    def get_controllers(self) -> List[Dict[str, Any]]:
        """Get list of registered algorithm controllers."""
        return [
            {
                **controller,
                "inputs": [spec.to_dict() for spec in controller["inputs"]],
            }
            for controller in self._controllers.values()
        ]

    def get_controller(self, controller_name: str) -> Dict[str, Any]:
        """Return internal controller metadata."""
        if controller_name not in self._controllers:
            raise KeyError(f"Controller '{controller_name}' not found")
        return self._controllers[controller_name]

    def get_controller_with_compatibility(
        self, controller_name: str, inputs: List[Any]
    ) -> Dict[str, Any]:
        """
        Get controller info with compatibility check and parameters.

        Args:
            controller_name: Name of the registered controller
            inputs: Ordered data inputs to check for compatibility

        Returns:
            Dictionary with controller info, compatibility status, and parameters
        """
        if controller_name not in self._controllers:
            return {
                "name": controller_name,
                "compatible": False,
                "error": "Controller not found",
            }

        controller = self._controllers[controller_name]
        algo_id = controller["id"]

        try:
            # Try to get algorithm properties - if this succeeds, the algorithm is compatible
            props = imfusion.algorithm.get_properties(algo_id, inputs)
            parameters = self._describe_parameters(props)

            return {
                "id": algo_id,
                "name": controller_name,
                "compatible": True,
                "parameters": parameters,
            }

        except imfusion.IncompatibleError:
            return {
                "id": algo_id,
                "name": controller_name,
                "compatible": False,
                "parameters": {},
            }
        except Exception as e:
            logger.warning(f"Error checking compatibility for {controller_name}: {e}")
            return {
                "id": algo_id,
                "name": controller_name,
                "compatible": False,
                "error": str(e),
                "parameters": {},
            }

    def discover_compatible_algorithms(self, inputs: List[Any]) -> List[Dict[str, Any]]:
        """
        Discover all algorithms compatible with the given inputs.

        Args:
            inputs: Ordered data inputs to test for compatibility

        Returns:
            List of dictionaries containing algorithm info:
                - id: Algorithm ID (e.g., 'Base.MorphologicalOperations')
                - name: Display name
                - properties: Configuration parameters
        """
        if not self._generic_panel_enabled:
            return []

        compatible_algorithms = []
        available_algos = imfusion.algorithm.list_available()

        logger.info(f"Testing {len(available_algos)} algorithms for compatibility")

        for algo_id in available_algos:
            try:
                # Try to get algorithm properties - if this succeeds, the algorithm is compatible
                props = imfusion.algorithm.get_properties(algo_id, inputs)
                parameters = self._describe_parameters(props)

                # Algorithm is compatible
                algo_info = {
                    "id": algo_id,
                    "name": self._get_display_name(algo_id),
                    "parameters": parameters,
                }

                compatible_algorithms.append(algo_info)
                logger.debug(f"Compatible: {algo_id}")

            except imfusion.IncompatibleError as e:
                # Algorithm not compatible - skip
                logger.debug(f"Incompatible: {algo_id} - {e}")
                continue
            except Exception as e:
                # Other errors - log and skip
                logger.warning(f"Error testing {algo_id}: {e}")
                continue

        logger.info(f"Found {len(compatible_algorithms)} compatible algorithms")
        return compatible_algorithms

    def execute_algorithm(
        self,
        algo_id: str,
        inputs: List[Any],
        parameters: Optional[Any] = None,
        result_input_index: int = 0,
        require_enabled: bool = True,
    ) -> List[Any]:
        """
        Execute an algorithm with given parameters.

        Args:
            algo_id: Algorithm ID
            inputs: Ordered algorithm inputs
            parameters: Optional parameter dictionary

        Returns:
            Algorithm outputs, or the configured input for in-place algorithms
        """
        if require_enabled and not self._execution_enabled:
            raise RuntimeError("Algorithm support is not enabled")

        logger.info(f"Executing algorithm: {algo_id}")
        logger.debug(f"Parameters: {parameters}")

        # Create properties object if parameters provided
        if isinstance(parameters, imfusion.Properties):
            props = parameters
        else:
            props = imfusion.Properties()
        if parameters and not isinstance(parameters, imfusion.Properties):
            for key, value in parameters.items():
                props[key] = value
                logger.debug(f"Set parameter {key} = {value}")

        # Execute the algorithm
        try:
            output_data = imfusion.algorithm.execute(algo_id, inputs, props)

            # Preserve every explicit algorithm output.
            if output_data and len(output_data) > 0:
                logger.info(f"Algorithm produced {len(output_data)} output(s)")
                return list(output_data)
            else:
                # No output - assume in-place modification
                logger.info("Algorithm executed in-place (no output)")
                return [inputs[result_input_index]]

        except Exception as e:
            logger.error(f"Error executing algorithm {algo_id}: {e}")
            raise

    def _describe_parameters(self, props: Any) -> Dict[str, Any]:
        """Serialize readable properties and their controller metadata."""
        parameters = {}
        for param_name in props.params():
            try:
                value = props[param_name]
                parameter_type = self._infer_type(value)
                serialized_value = self._serialize_value(value)
                descriptor = {
                    "name": param_name,
                    "label": param_name,
                    "value": serialized_value,
                    "default": serialized_value,
                    "type": parameter_type,
                }
                if isinstance(value, imfusion.Properties.EnumStringParam):
                    descriptor["options"] = sorted(value.admitted_values)
                for key, raw_value in props.param_attributes(param_name):
                    normalized_key = {
                        "min": "min",
                        "max": "max",
                        "step": "step",
                        "unit": "unit",
                        "description": "description",
                    }.get(key)
                    if normalized_key is not None:
                        descriptor[normalized_key] = self._parse_attribute(
                            raw_value, parameter_type
                        )
                parameters[param_name] = descriptor
            except Exception as e:
                logger.warning(f"Could not get info for parameter {param_name}: {e}")
                continue
        return parameters

    def _get_display_name(self, algo_id: str) -> str:
        """Get a display name for the algorithm."""
        # Remove module prefix for cleaner display
        if "." in algo_id:
            return algo_id.split(".", 1)[1]
        return algo_id

    def _serialize_value(self, value: Any) -> Any:
        """Serialize a parameter value for JSON transmission."""
        if isinstance(value, imfusion.Properties.EnumStringParam):
            return value.value
        # Handle common types
        if isinstance(value, (int, float, str, bool)):
            return value
        elif isinstance(value, list):
            return [self._serialize_value(v) for v in value]
        elif hasattr(value, "__int__"):
            return int(value)
        elif hasattr(value, "__float__"):
            return float(value)
        else:
            return str(value)

    def _infer_type(self, value: Any) -> str:
        """Infer the parameter type for UI generation."""
        if isinstance(value, imfusion.Properties.EnumStringParam):
            return "choice"
        # Check by value type
        if isinstance(value, bool):
            return "bool"
        elif isinstance(value, int):
            return "int"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, str):
            return "string"
        else:
            return "string"

    def _parse_attribute(self, value: str, parameter_type: str) -> Any:
        """Convert string-valued SDK parameter attributes for the web client."""
        if parameter_type == "int":
            try:
                return int(value)
            except ValueError:
                return value
        if parameter_type == "float":
            try:
                return float(value)
            except ValueError:
                return value
        return value
