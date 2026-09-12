"""
PRAMAAN minimal ONNX writer — for testing only.

Writes valid ONNX protobuf bytes without requiring the 'onnx' package.
Uses raw protobuf encoding against the ONNX protobuf schema.

Tests only. NOT for production use.

ONNX protobuf field numbers (proto2 schema):
  ModelProto:     ir_version=1, opset_import=8, graph=7
  GraphProto:     node=1, name=2, initializer=5, input=11, output=12
  NodeProto:      input=1, output=2, op_type=4
  ValueInfoProto: name=1, type=2
  TypeProto:      tensor_type=1 (oneof value)
  TensorTypeProto: elem_type=1, shape=2
  TensorShapeProto: dim=1
  Dimension:      dim_value=1, dim_param=2
  TensorProto:    dims=1, data_type=2, name=8, raw_data=9
  OperatorSetIdProto: domain=1, version=2
  DataType:       FLOAT=1
"""

from __future__ import annotations

import struct


# ---------------------------------------------------------------------------
# Protobuf wire-format primitives
# ---------------------------------------------------------------------------

def _varint(n: int) -> bytes:
    """Encode a non-negative integer as a protobuf base-128 varint."""
    out = []
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _tag_varint(field_num: int) -> bytes:
    """Tag byte(s) for a varint field (wire type 0)."""
    return _varint((field_num << 3) | 0)


def _tag_len(field_num: int) -> bytes:
    """Tag byte(s) for a length-delimited field (wire type 2)."""
    return _varint((field_num << 3) | 2)


def _enc_varint(field_num: int, value: int) -> bytes:
    """Encode a varint field."""
    return _tag_varint(field_num) + _varint(value)


def _enc_bytes(field_num: int, data: bytes) -> bytes:
    """Encode a length-delimited field (bytes / string / embedded message)."""
    return _tag_len(field_num) + _varint(len(data)) + data


def _enc_str(field_num: int, s: str) -> bytes:
    """Encode a string field."""
    return _enc_bytes(field_num, s.encode("utf-8"))


def _f32_raw(values: list[float]) -> bytes:
    """Pack floats as little-endian float32 bytes."""
    return struct.pack(f"<{len(values)}f", *values)


# ---------------------------------------------------------------------------
# ONNX DataType enum
# ---------------------------------------------------------------------------
_FLOAT = 1  # TensorProto.DataType.FLOAT


# ---------------------------------------------------------------------------
# TypeProto (for ValueInfoProto)
# ---------------------------------------------------------------------------

def _type_proto_float(shape: list[int]) -> bytes:
    """
    Encode a TypeProto for a float32 tensor.

    TypeProto { tensor_type { elem_type: FLOAT shape { dim { dim_value: d } ... } } }

    Returns the raw bytes of the TypeProto message (not wrapped in a field tag).
    """
    # Build TensorShapeProto: repeated Dimension { dim_value }
    dims_bytes = b""
    for d in shape:
        # Dimension: field 1 = dim_value (varint)
        dim_msg = _enc_varint(1, d)
        # TensorShapeProto: field 1 = dim (length-delimited message)
        dims_bytes += _enc_bytes(1, dim_msg)

    # TensorTypeProto: field 1 = elem_type, field 2 = shape
    tensor_type_msg = _enc_varint(1, _FLOAT) + _enc_bytes(2, dims_bytes)

    # TypeProto: field 1 = tensor_type (oneof: tensor type variant)
    type_proto_msg = _enc_bytes(1, tensor_type_msg)

    return type_proto_msg


# ---------------------------------------------------------------------------
# ValueInfoProto
# ---------------------------------------------------------------------------

def _value_info(name: str, shape: list[int]) -> bytes:
    """
    Encode a ValueInfoProto for a named float32 tensor.
    ValueInfoProto: field 1 = name, field 2 = type (TypeProto)
    """
    return _enc_str(1, name) + _enc_bytes(2, _type_proto_float(shape))


# ---------------------------------------------------------------------------
# NodeProto
# ---------------------------------------------------------------------------

def _node(op_type: str, inputs: list[str], outputs: list[str]) -> bytes:
    """
    Encode a NodeProto.
    NodeProto: field 1 = input (repeated string), field 2 = output, field 4 = op_type
    """
    payload = b""
    for i in inputs:
        payload += _enc_str(1, i)
    for o in outputs:
        payload += _enc_str(2, o)
    payload += _enc_str(4, op_type)
    return payload


# ---------------------------------------------------------------------------
# TensorProto (initializer)
# ---------------------------------------------------------------------------

def _initializer_float(name: str, shape: list[int], values: list[float]) -> bytes:
    """
    Encode a TensorProto for a float32 initializer.
    TensorProto:
      field 1 = dims        (repeated int64, non-packed)
      field 2 = data_type   (FLOAT = 1)
      field 8 = name        (string)
      field 9 = raw_data    (bytes, little-endian float32)
    """
    payload = b""
    # field 1: dims (repeated int64, one field per dimension)
    for d in shape:
        payload += _enc_varint(1, d)
    # field 2: data_type = FLOAT
    payload += _enc_varint(2, _FLOAT)
    # field 8: name
    payload += _enc_str(8, name)
    # field 9: raw_data
    payload += _enc_bytes(9, _f32_raw(values))
    return payload


# ---------------------------------------------------------------------------
# OperatorSetIdProto
# ---------------------------------------------------------------------------

def _opset(domain: str = "", version: int = 17) -> bytes:
    """
    Encode an OperatorSetIdProto.
    field 1 = domain, field 2 = version
    """
    return _enc_str(1, domain) + _enc_varint(2, version)


# ---------------------------------------------------------------------------
# GraphProto
# ---------------------------------------------------------------------------

def _graph(
    name: str,
    nodes: list[bytes],
    inputs: list[bytes],
    outputs: list[bytes],
    initializers: list[bytes] | None = None,
) -> bytes:
    """
    Encode a GraphProto.
    GraphProto:
      field 1  = node (NodeProto, repeated)
      field 2  = name (string)
      field 5  = initializer (TensorProto, repeated)
      field 11 = input (ValueInfoProto, repeated)
      field 12 = output (ValueInfoProto, repeated)
    """
    payload = b""
    for node in nodes:
        payload += _enc_bytes(1, node)
    payload += _enc_str(2, name)
    if initializers:
        for init in initializers:
            payload += _enc_bytes(5, init)
    for inp in inputs:
        payload += _enc_bytes(11, inp)
    for out in outputs:
        payload += _enc_bytes(12, out)
    return payload


# ---------------------------------------------------------------------------
# ModelProto
# ---------------------------------------------------------------------------

def _model(graph: bytes, ir_version: int = 8, opset_version: int = 17) -> bytes:
    """
    Encode a ModelProto.
    ModelProto:
      field 1 = ir_version (int64)
      field 7 = graph (GraphProto)
      field 8 = opset_import (OperatorSetIdProto, repeated)
    """
    return (
        _enc_varint(1, ir_version)
        + _enc_bytes(7, graph)
        + _enc_bytes(8, _opset("", opset_version))
    )


# ---------------------------------------------------------------------------
# Public model factories
# ---------------------------------------------------------------------------

def make_relu_model(input_shape: list[int] | None = None) -> bytes:
    """
    Create a minimal valid ONNX model: Y = Relu(X).

    Returns raw ONNX protobuf bytes loadable by ORT.
    """
    if input_shape is None:
        input_shape = [1, 3]

    x_vi = _value_info("X", input_shape)
    y_vi = _value_info("Y", input_shape)
    relu = _node("Relu", ["X"], ["Y"])

    graph = _graph("relu_graph", [relu], [x_vi], [y_vi])
    return _model(graph)


def make_add_bias_model(
    bias_values: list[float] | None = None,
    input_shape: list[int] | None = None,
) -> bytes:
    """
    Create a minimal ONNX model: Y = X + B, where B is a learnable bias.

    Returns raw ONNX protobuf bytes loadable by ORT.
    Changing bias_values changes the model's behavioral output.
    """
    if input_shape is None:
        input_shape = [1, 3]
    if bias_values is None:
        bias_values = [1.0] * input_shape[-1]

    # Inputs: X (data input), B is NOT a graph input — it's an initializer only
    x_vi = _value_info("X", input_shape)
    y_vi = _value_info("Y", input_shape)

    bias_init = _initializer_float("B", input_shape, bias_values)
    add = _node("Add", ["X", "B"], ["Y"])

    graph = _graph("add_bias_graph", [add], [x_vi], [y_vi], initializers=[bias_init])
    return _model(graph)


def make_nan_bias_model(input_shape: list[int] | None = None) -> bytes:
    """Create an ONNX model with a NaN weight in its initializer."""
    if input_shape is None:
        input_shape = [1, 3]
    return make_add_bias_model([float("nan")] * input_shape[-1], input_shape=input_shape)


def make_inf_bias_model(input_shape: list[int] | None = None) -> bytes:
    """Create an ONNX model with an Inf weight in its initializer."""
    if input_shape is None:
        input_shape = [1, 3]
    return make_add_bias_model([float("inf")] * input_shape[-1], input_shape=input_shape)


def make_extreme_bias_model(input_shape: list[int] | None = None) -> bytes:
    """Create an ONNX model with extreme weight magnitude (|w| > 1e5)."""
    if input_shape is None:
        input_shape = [1, 3]
    return make_add_bias_model([1e5, -1e5, 2e5][: input_shape[-1]], input_shape=input_shape)


def make_multi_layer_model(input_shape: list[int] | None = None) -> bytes:
    """Create a 2-node ONNX model: H = Add(X, B), Y = Relu(H)."""
    if input_shape is None:
        input_shape = [1, 3]

    x_vi = _value_info("X", input_shape)
    y_vi = _value_info("Y", input_shape)
    bias_init = _initializer_float("B", input_shape, [0.5] * input_shape[-1])

    add = _node("Add", ["X", "B"], ["H"])
    relu = _node("Relu", ["H"], ["Y"])

    graph = _graph("multi_layer_graph", [add, relu], [x_vi], [y_vi], initializers=[bias_init])
    return _model(graph)


def make_dead_representation_model(input_shape: list[int] | None = None) -> bytes:
    """Create an ONNX model where all outputs are clamped to 0: Y = Relu(X + (-1000))."""
    if input_shape is None:
        input_shape = [1, 3]

    x_vi = _value_info("X", input_shape)
    y_vi = _value_info("Y", input_shape)
    bias_init = _initializer_float("B", input_shape, [-1000.0] * input_shape[-1])

    add = _node("Add", ["X", "B"], ["H"])
    relu = _node("Relu", ["H"], ["Y"])

    graph = _graph("dead_repr_graph", [add, relu], [x_vi], [y_vi], initializers=[bias_init])
    return _model(graph)
