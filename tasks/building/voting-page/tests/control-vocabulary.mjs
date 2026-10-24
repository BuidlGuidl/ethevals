export class CouldNotDrive extends Error {
  constructor(message) { super(`could not drive: ${message}`); }
}

export async function firstVisible(locator) {
  for (const item of await locator.all()) if (await item.isVisible()) return item;
  return null;
}
