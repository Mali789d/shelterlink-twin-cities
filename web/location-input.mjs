// Explicit manual coordinates only. No geocoder, GPS request, network or storage.
// Reject incomplete/ambiguous strings instead of guessing a ZIP, address or direction.
export function parseCoordinates(input) {
  if (typeof input !== 'string' || input.length > 100) {
    throw new Error('Enter latitude, longitude');
  }
  const match = input.trim().match(
    /^([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*,\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))$/,
  );
  if (!match) throw new Error('Use decimal latitude, longitude separated by a comma');
  const latitude = Number(match[1]);
  const longitude = Number(match[2]);
  if (!Number.isFinite(latitude) || Math.abs(latitude) > 90
      || !Number.isFinite(longitude) || Math.abs(longitude) > 180) {
    throw new Error('Latitude must be -90 to 90 and longitude -180 to 180');
  }
  return Object.freeze({latitude, longitude});
}
