import copy

import pytest
import torch
from torch_sparse import SparseTensor

from torch_geometric.nn import GCNConv
from torch_geometric.nn.conv.gcn_conv import gcn_norm
from torch_geometric.testing import is_full_test
from torch_geometric.utils import to_torch_coo_tensor


def test_gcn_conv():
    x = torch.randn(4, 16)
    edge_index = torch.tensor([[0, 0, 0, 1, 2, 3], [1, 2, 3, 0, 0, 0]])
    row, col = edge_index
    value = torch.rand(row.size(0))
    adj2 = SparseTensor(row=row, col=col, value=value, sparse_sizes=(4, 4))
    adj1 = adj2.set_value(None)
    adj3 = adj1.to_torch_sparse_csc_tensor()
    adj4 = adj2.to_torch_sparse_csc_tensor()

    conv = GCNConv(16, 32)
    assert str(conv) == 'GCNConv(16, 32)'
    out1 = conv(x, edge_index)
    assert out1.size() == (4, 32)
    assert torch.allclose(conv(x, adj1.t()), out1, atol=1e-6)
    assert torch.allclose(conv(x, adj3.t()), out1, atol=1e-6)
    out2 = conv(x, edge_index, value)
    assert out2.size() == (4, 32)
    assert torch.allclose(conv(x, adj2.t()), out2, atol=1e-6)
    assert torch.allclose(conv(x, adj4.t()), out2, atol=1e-6)

    if is_full_test():
        t = '(Tensor, Tensor, OptTensor) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert jit(x, edge_index).tolist() == out1.tolist()
        assert jit(x, edge_index, value).tolist() == out2.tolist()

        t = '(Tensor, SparseTensor, OptTensor) -> Tensor'
        jit = torch.jit.script(conv.jittable(t))
        assert torch.allclose(jit(x, adj1.t()), out1, atol=1e-6)
        assert torch.allclose(jit(x, adj2.t()), out2, atol=1e-6)

    conv.cached = True
    conv(x, edge_index)
    assert conv(x, edge_index).tolist() == out1.tolist()
    conv(x, adj1.t())
    assert torch.allclose(conv(x, adj1.t()), out1, atol=1e-6)


def test_gcn_conv_with_decomposed_layers():
    x = torch.randn(4, 16)
    edge_index = torch.tensor([[0, 0, 0, 1, 2, 3], [1, 2, 3, 0, 0, 0]])

    conv = GCNConv(16, 32)

    decomposed_conv = copy.deepcopy(conv)
    decomposed_conv.decomposed_layers = 2

    out1 = conv(x, edge_index)
    out2 = decomposed_conv(x, edge_index)
    assert torch.allclose(out1, out2)

    if is_full_test():
        t = '(Tensor, Tensor, OptTensor) -> Tensor'
        jit = torch.jit.script(decomposed_conv.jittable(t))
        assert jit(x, edge_index).tolist() == out1.tolist()


def test_gcn_conv_with_sparse_input_feature():
    x = torch.sparse_coo_tensor(
        indices=torch.tensor([[0, 0], [0, 1]]),
        values=torch.tensor([1., 1.]),
        size=torch.Size([4, 16]),
    )
    edge_index = torch.tensor([[0, 0, 0, 1, 2, 3], [1, 2, 3, 0, 0, 0]])

    conv = GCNConv(16, 32)
    assert conv(x, edge_index).size() == (4, 32)


def test_static_gcn_conv():
    x = torch.randn(3, 4, 16)
    edge_index = torch.tensor([[0, 0, 0, 1, 2, 3], [1, 2, 3, 0, 0, 0]])

    conv = GCNConv(16, 32)
    out = conv(x, edge_index)
    assert out.size() == (3, 4, 32)


def test_gcn_conv_norm():
    x = torch.randn(4, 16)
    edge_index = torch.tensor([[0, 0, 0], [1, 2, 3]])
    row, col = edge_index

    conv = GCNConv(16, 32, flow="source_to_target")
    out1 = conv(x, edge_index)
    conv.flow = "target_to_source"
    out2 = conv(x, edge_index.flip(0))
    assert torch.allclose(out1, out2, atol=1e-6)


@pytest.mark.parametrize('requires_grad', [False, True])
@pytest.mark.parametrize('layout', [torch.sparse_coo, torch.sparse_csr])
def test_gcn_norm_gradient(requires_grad, layout):
    edge_index = torch.tensor([[0, 0, 0, 1, 2, 3], [1, 2, 3, 0, 0, 0]])
    edge_weight = torch.ones(edge_index.size(1), requires_grad=requires_grad)
    adj = to_torch_coo_tensor(edge_index, edge_weight)
    if layout == torch.sparse_csr:
        adj = adj.to_sparse_csr()

    # TODO Sparse CSR tensor does not yet inherit `requires_grad` from `value`.
    if layout == torch.sparse_csr:
        assert not gcn_norm(adj)[0].requires_grad
    else:
        assert adj.requires_grad == gcn_norm(adj)[0].requires_grad
