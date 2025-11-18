"""
Parser for reading and analyzing Swagger/OpenAPI specifications.
Supports loading from local files and URLs.
"""

import json
import yaml
import logging
import httpx
from urllib.parse import urlparse
from typing import Dict, Any, Optional, Set

logger = logging.getLogger(__name__)


class SwaggerParser:
    """Parser that reads a Swagger/OpenAPI spec with $ref resolution."""

    def __init__(self, spec_path_or_url: str):
        self.spec_path = spec_path_or_url
        self.spec = None
        self.spec_version = None
        self.is_url = self._is_url(spec_path_or_url)
        self.load_spec()
        self.detect_version()

    def _is_url(self, path: str) -> bool:
        """Return True if the given path looks like a URL."""
        try:
            result = urlparse(path)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    def load_spec(self):
        """Load the spec from disk or a URL."""
        try:
            if self.is_url:
                self._load_from_url()
            else:
                self._load_from_file()
            logger.info(f"Specification loaded: {self.spec_path}")
        except Exception as e:
            logger.error(f"Failed to load specification: {e}")
            raise

    def _load_from_url(self):
        """Load specification from a URL."""
        logger.info(f"Fetching specification from URL: {self.spec_path}")
        
        try:
            response = httpx.get(self.spec_path, timeout=30.0, follow_redirects=True)
            response.raise_for_status()
            
            # Detect format via Content-Type
            content_type = response.headers.get('content-type', '').lower()
            
            # Fall back to file extension if Content-Type is vague
            if 'json' in content_type or self.spec_path.endswith('.json'):
                self.spec = response.json()
                logger.debug("Format detected: JSON (Content-Type or extension)")
            elif 'yaml' in content_type or 'yml' in content_type or \
                 self.spec_path.endswith(('.yaml', '.yml')):
                self.spec = yaml.safe_load(response.text)
                logger.debug("Format detected: YAML (Content-Type or extension)")
            else:
                # Try to guess based on body content
                try:
                    self.spec = response.json()
                    logger.info("Format detected: JSON (content sniffing)")
                except json.JSONDecodeError:
                    try:
                        self.spec = yaml.safe_load(response.text)
                        logger.info("Format detected: YAML (content sniffing)")
                    except yaml.YAMLError:
                        raise ValueError(
                            "Unable to determine spec format. "
                            "Use .json or .yaml/.yml in the URL or make sure the server returns a proper Content-Type."
                        )
            
            if not self.spec:
                raise ValueError("Specification payload is empty")
            
            logger.info(f"Specification fetched successfully ({len(response.content)} bytes)")
            
        except httpx.TimeoutException:
            raise ConnectionError(f"Timeout while loading spec from URL: {self.spec_path}")
        except httpx.HTTPStatusError as e:
            raise ConnectionError(f"HTTP error {e.response.status_code} while loading spec: {e}")
        except httpx.RequestError as e:
            raise ConnectionError(f"Network error while loading spec: {e}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON from URL: {e}")
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse YAML from URL: {e}")

    def _load_from_file(self):
        """Load specification from a local file."""
        try:
            with open(self.spec_path, 'r', encoding='utf-8') as f:
                if self.spec_path.endswith('.json'):
                    self.spec = json.load(f)
                elif self.spec_path.endswith(('.yaml', '.yml')):
                    self.spec = yaml.safe_load(f)
                else:
                    raise ValueError("Only .json and .yaml/.yml files are supported")
        except FileNotFoundError:
            raise FileNotFoundError(f"Specification file not found: {self.spec_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON file: {e}")
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse YAML file: {e}")

    def detect_version(self):
        """Detect whether the spec is Swagger 2.0 or OpenAPI 3.x."""
        if 'openapi' in self.spec:
            self.spec_version = 'openapi3'
            logger.info("Detected OpenAPI 3.x specification")
        elif 'swagger' in self.spec:
            self.spec_version = 'swagger2'
            logger.info("Detected Swagger 2.0 specification")
        else:
            logger.warning("Unable to determine spec version, assuming Swagger 2.0")
            self.spec_version = 'swagger2'

    def resolve_ref(self, ref_path: str) -> Dict[str, Any]:
        """Resolve a $ref pointer within the spec."""
        if not ref_path.startswith('#/'):
            logger.warning(f"External references are not supported: {ref_path}")
            return {}

        # remove '#/' and split path
        path_parts = ref_path[2:].split('/')
        
        # determine root section based on version
        if self.spec_version == 'openapi3':
            # OpenAPI 3.0 keeps schemas under components/schemas
            if path_parts[0] == 'components' and path_parts[1] == 'schemas':
                schema_name = path_parts[2]
                return self.spec.get('components', {}).get('schemas', {}).get(schema_name, {})
        else:
            # Swagger 2.0 keeps schemas under definitions
            if path_parts[0] == 'definitions':
                schema_name = path_parts[1]
                return self.spec.get('definitions', {}).get(schema_name, {})

        # fall back to path traversal
        resolved = self.spec
        for part in path_parts:
            if isinstance(resolved, dict):
                resolved = resolved.get(part, {})
            else:
                return {}
        return resolved if isinstance(resolved, dict) else {}

    def resolve_refs_recursive(self, obj: Any, visited_refs: Optional[Set[str]] = None) -> Any:
        """Recursively resolve all $ref pointers within the object."""
        if visited_refs is None:
            visited_refs = set()

        if isinstance(obj, dict):
            if '$ref' in obj:
                ref_path = obj['$ref']
                if ref_path in visited_refs:
                    logger.warning(f"Circular reference detected: {ref_path}")
                    return {"$ref": ref_path, "_resolved": "circular_reference"}
                
                visited_refs.add(ref_path)
                resolved = self.resolve_ref(ref_path)
                if resolved:
                    # Recursively resolve the referenced object
                    return self.resolve_refs_recursive(resolved, visited_refs)
                return obj
            
            return {k: self.resolve_refs_recursive(v, visited_refs) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.resolve_refs_recursive(item, visited_refs) for item in obj]
        return obj

    def get_paths(self) -> Dict[str, Dict[str, Any]]:
        """Return the `paths` dictionary."""
        return self.spec.get("paths", {})

    def get_operation_details(self, path: str, method: str) -> Dict[str, Any]:
        """Return operation details with resolved $refs."""
        paths = self.get_paths()
        if path not in paths:
            return {}

        method_lower = method.lower()
        if method_lower not in paths[path]:
            return {}

        operation = paths[path][method_lower].copy()
        # resolve deep $ref entries
        return self.resolve_refs_recursive(operation)

    def get_relevant_schemas(self, operation: Dict[str, Any]) -> Dict[str, Any]:
        """Extract only the schemas relevant for the operation."""
        schemas = {}
        
        # Pull schemas from requestBody (OpenAPI 3.x)
        request_body = operation.get('requestBody', {})
        if isinstance(request_body, dict):
            content = request_body.get('content', {})
            for content_type, content_schema in content.items():
                schema_ref = content_schema.get('schema', {}).get('$ref', '')
                if schema_ref:
                    schema_name = schema_ref.split('/')[-1]
                    if self.spec_version == 'openapi3':
                        schemas[schema_name] = self.spec.get('components', {}).get('schemas', {}).get(schema_name, {})
                    else:
                        schemas[schema_name] = self.spec.get('definitions', {}).get(schema_name, {})

        # Pull body parameter schemas (Swagger 2.0)
        parameters = operation.get('parameters', [])
        for param in parameters:
            if param.get('in') == 'body':
                schema_ref = param.get('schema', {}).get('$ref', '')
                if schema_ref:
                    schema_name = schema_ref.split('/')[-1]
                    if self.spec_version == 'openapi3':
                        schemas[schema_name] = self.spec.get('components', {}).get('schemas', {}).get(schema_name, {})
                    else:
                        schemas[schema_name] = self.spec.get('definitions', {}).get(schema_name, {})
        
        # Resolve nested $refs
        resolved_schemas = {}
        for name, schema in schemas.items():
            resolved_schemas[name] = self.resolve_refs_recursive(schema)
        
        return resolved_schemas

    def get_minimal_context(self) -> Dict[str, Any]:
        """Return a trimmed context block without all schemas."""
        context = {
            "info": self.spec.get("info", {}),
            "host": self.spec.get("host", ""),
            "basePath": self.spec.get("basePath", ""),
            "servers": self.spec.get("servers", []),  # OpenAPI 3.0
            "securityDefinitions": self.spec.get("securityDefinitions", {}),
            "security": self.spec.get("security", {}),
            "components": {
                "securitySchemes": self.spec.get("components", {}).get("securitySchemes", {})
            } if self.spec_version == 'openapi3' else {}
        }
        return context

