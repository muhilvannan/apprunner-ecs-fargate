FROM public.ecr.aws/docker/library/node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev

COPY server.js index.html ./

EXPOSE 3001

CMD ["node", "server.js"]
