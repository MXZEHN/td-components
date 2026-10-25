# Unit quad in XY facing +Z, with uv, shared by every node card.
def onCook(scriptOp):
    scriptOp.clear()
    scriptOp.vertexAttribs.create('uv', (0.0, 0.0, 0.0))
    corners = ((-0.5, -0.5, 0, 0), (0.5, -0.5, 1, 0), (0.5, 0.5, 1, 1), (-0.5, 0.5, 0, 1))
    poly = scriptOp.appendPoly(4, closed=True, addPoints=True)
    for i, (x, y, u, v) in enumerate(corners):
        poly[i].point.P = (x, y, 0.0)
        poly[i].uv = (u, v, 0.0)
    return
