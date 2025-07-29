function reply = sendPipeMessage(msg, pipePath)
%SENDPIPEMESSAGE  Send a JSON message to a Python named‑pipe server and return its reply.
%
%   reply = SENDPIPEMESSAGE(MSG)
%   reply = SENDPIPEMESSAGE(MSG, PIPEPATH)
%
%   Inputs
%   ------
%   MSG       (struct | containers.Map):
%       Payload to transmit; converted to JSON with jsonencode.
%   PIPEPATH  (char, optional):
%       Full Windows pipe path. Default: '\\\\.\\pipe\\MatPy'.
%
%   Each invocation:
%       1. Opens a NamedPipeClientStream.
%       2. Writes one UTF‑8, newline‑terminated JSON packet.
%       3. Blocks until a newline‑terminated reply is read.
%       4. Closes the stream.
%
%   Example
%   -------
%       reply = sendPipeMessage(struct("cmd","TASK","action","start"));
%
%   Notes
%   -----
%   * For high‑frequency messaging, wrap this helper in a persistent
%     object that re‑uses the stream instead of reconnecting each time.
%   * Requires MATLAB R2019b+ on Windows with .NET enabled.
%
%   © 2025  Lab Pipelines — GPL‑3.0
%--------------------------------------------------------------------------

if nargin < 2 || isempty(pipePath)
    pipePath = '\\.\pipe\MatPy';
end

if ~ischar(pipePath) && ~isstring(pipePath)
    error('sendPipeMessage:BadPipePath','PIPEPATH must be a char or string.');
end
pipePath = char(pipePath);

% NamedPipeClientStream expects server + pipe name, not full path.
tokens = regexp(pipePath, '\\\\.\\pipe\\(.+)$', 'tokens', 'once');
if isempty(tokens)
    error('sendPipeMessage:InvalidPath','PIPEPATH must look like "\\\\.\\pipe\\<name>".');
end
pipeName = tokens{1};

% Ensure .NET is available
if ~usejava('net')
    error('sendPipeMessage:JavaUnavailable','Java/.NET support is required on this platform.');
end

import System.IO.*
import System.IO.Pipes.*
import System.Text.*

% Convert payload
payload = jsonencode(msg) + newline;  %#ok<STRNCAT> add LF terminator

% Open & connect
pipe = NamedPipeClientStream('.', pipeName, PipeDirection.InOut, ...
    PipeOptions.None, TokenImpersonationLevel.Impersonation);

try
    pipe.Connect(1000);  % ms timeout
catch ME
    error('sendPipeMessage:ConnectFailed', ...
        'Unable to connect to pipe "%s": %s', pipeName, ME.message);
end

try
    writer = StreamWriter(pipe, UTF8Encoding(false));
    reader = StreamReader(pipe, UTF8Encoding(false));

    writer.AutoFlush = true;
    writer.Write(payload);

    responseLine = char(reader.ReadLine());
    if isempty(responseLine)
        reply = struct('error','empty_response');
    else
        reply = jsondecode(responseLine);
    end
catch ME
    error('sendPipeMessage:IOError','I/O error on pipe "%s": %s', pipeName, ME.message);
end

pipe.Close();
end