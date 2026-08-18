export function createLatestQueue(worker) {
  let pending;
  let running = null;

  async function drain() {
    let error;
    try {
      while (pending !== undefined) {
        const value = pending;
        pending = undefined;
        try {
          await worker(value);
        } catch (workerError) {
          error ??= workerError;
        }
      }
    } finally {
      running = null;
      if (pending !== undefined) running = drain();
    }
    if (error) throw error;
  }

  const enqueue = (value) => {
    pending = value;
    if (!running) running = drain();
    return running;
  };
  enqueue.flush = () => running ?? Promise.resolve();
  return enqueue;
}
