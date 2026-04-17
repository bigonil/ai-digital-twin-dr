/**
 * A-Frame mock for aframe-extras
 *
 * aframe-extras is a sub-dependency of react-force-graph (via 3d-force-graph-vr)
 * but we don't use VR/AR features. This mock prevents "AFRAME is not defined" errors
 * while allowing the dependency tree to resolve normally.
 */

export default {
  registerComponent: () => {},
  registerSystem: () => {},
  registerShader: () => {},
  registerPrimitive: () => {},
  registerGeometry: () => {},
  version: '1.7.0',
}
