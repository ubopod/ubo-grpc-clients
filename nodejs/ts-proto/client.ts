import { credentials } from "@grpc/grpc-js";
import {
  StoreServiceClient,
  DispatchActionRequest,
} from "./generated/store/v1/store";
import { Chime } from "./generated/ubo/v1/ubo";

// Create a client instance
const client = new StoreServiceClient(
  "localhost:50051",
  credentials.createInsecure(),
);

// Prepare the request
const request: DispatchActionRequest = {
  action: {
    notificationsAddAction: {
      notification: {
        title: "Hello, World!",
        content: "This is a notification",
        chime: Chime.CHIME_DONE,
        actions: {
          items: [
            {
              notificationDispatchItem: {
                operation: {
                  uboAction: {
                    audioPlayChimeAction: { name: "add" },
                  },
                },
                icon: "󰑣",
                color: "#ff0000",
                backgroundColor: "#00ff00",
              },
            },
          ],
        },
      },
    },
  },
};

// Make a unary RPC call
client.dispatchAction(request, (error, response) => {
  if (error) {
    console.error("Error:", error);
    return;
  }
  console.log("Response:", response);
});
