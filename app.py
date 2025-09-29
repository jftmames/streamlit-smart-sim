import streamlit as st
from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider
from eth_tester import EthereumTester, PyEVMBackend
from solcx import compile_standard, install_solc
import time
import io
import csv

st.set_page_config(page_title="Sim Smart Contract (Streamlit)", layout="centered")

st.title("Simulación de Smart Contract: de contrato en castellano a Solidity")
st.caption("Cadena de pruebas en memoria (EthereumTester). No necesitas wallet.")

# -------------------- Helpers de estado --------------------
def boot_chain(force=False):
    """
    Inicializa una cadena Ethereum en memoria y resetea el estado de la app.
    """
    if force or "w3" not in st.session_state:
        backend = PyEVMBackend()
        tester = EthereumTester(backend=backend)
        w3 = Web3(EthereumTesterProvider(tester))
        st.session_state.w3 = w3
        st.session_state.cuentas = w3.eth.accounts
        st.session_state.vendedor = st.session_state.cuentas[0]
        st.session_state.comprador = st.session_state.cuentas[1]
        st.session_state.contract_addr = None
        st.session_state.event_log = []  # [{evento, info, tx, ts}]
boot_chain()

def push_event(nombre, info, txhash):
    st.session_state.event_log.append({
        "evento": nombre,
        "info": info,
        "tx": txhash.hex() if hasattr(txhash, "hex") else str(txhash),
        "ts": int(time.time())
    })

# -------------------- Contrato en castellano (texto base) --------------------
with st.expander("📜 Contrato en castellano (base didáctica)", expanded=True):
    st.markdown(
        """
**“Contrato básico de compraventa con pago y confirmación de entrega”**

1. **Partes**: Vendedor (A) y Comprador (B).  
2. **Objeto**: Entrega del bien/servicio descrito como “OBJETO”.  
3. **Precio**: “PRECIO” pagadero en un único pago.  
4. **Plazo**: La operación debe completarse antes de la **FECHA LÍMITE**.  
5. **Flujo**:  
   a) Ambas partes **firman** el contrato.  
   b) El Comprador **paga** el precio.  
   c) El Comprador **confirma la entrega**.  
   d) Tras la confirmación, el Vendedor **recibe los fondos**.  
6. **Cancelación**: Si se cancela antes de concluir, se devuelven los fondos al Comprador.
"""
    )

# -------------------- Código Solidity --------------------
SOLIDITY_SRC = """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract ContratoBasico {
    address public vendedor;
    address public comprador;
    string public objeto;
    uint256 public precioWei;
    uint256 public fechaLimite; // epoch (segundos)

    enum Estado { Borrador, Activo, Resuelto, Cancelado }
    Estado public estado;

    event Firmado(address vendedor, address comprador);
    event Pagado(address from, uint256 amount);
    event EntregaConfirmada(address by);
    event Cancelado(address by, uint256 devolucion);

    modifier soloPartes() {
        require(msg.sender == vendedor || msg.sender == comprador, "Solo partes");
        _;
    }

    constructor(
        address _comprador,
        string memory _objeto,
        uint256 _precioWei,
        uint256 _fechaLimite
    ) {
        vendedor = msg.sender;
        comprador = _comprador;
        objeto = _objeto;
        precioWei = _precioWei;
        fechaLimite = _fechaLimite;
        estado = Estado.Borrador;
    }

    function firmar() external soloPartes {
        require(estado == Estado.Borrador, "No en borrador");
        require(block.timestamp < fechaLimite, "Plazo vencido");
        estado = Estado.Activo;
        emit Firmado(vendedor, comprador);
    }

    function pagar() external payable {
        require(estado == Estado.Activo, "No activo");
        require(msg.sender == comprador, "Solo comprador");
        require(msg.value == precioWei, "Importe incorrecto");
        emit Pagado(msg.sender, msg.value);
    }

    function confirmarEntrega() external {
        require(estado == Estado.Activo, "No activo");
        require(msg.sender == comprador, "Solo comprador");
        estado = Estado.Resuelto;
        (bool ok, ) = vendedor.call{value: address(this).balance}("");
        require(ok, "Fallo pago a vendedor");
        emit EntregaConfirmada(msg.sender);
    }

    function cancelar() external soloPartes {
        require(
            estado == Estado.Activo || estado == Estado.Borrador,
            "No cancelable"
        );
        estado = Estado.Cancelado;
        uint256 saldo = address(this).balance;
        if (saldo > 0) {
            (bool ok, ) = comprador.call{value: saldo}("");
            require(ok, "Fallo devolucion");
        }
        emit Cancelado(msg.sender, saldo);
    }

    function tiempoRestante() external view returns (uint256) {
        if (block.timestamp >= fechaLimite) return 0;
        return fechaLimite - block.timestamp;
    }
}
"""

with st.expander("🧩 Código Solidity (traducción del contrato)", expanded=False):
    st.code(SOLIDITY_SRC, language="solidity")

# -------------------- Compilación --------------------
with st.status("Instalando/seleccionando compilador Solidity 0.8.24…", expanded=False) as status:
    install_solc("0.8.24")
    status.update(label="Compilando contrato…", state="running")
    compiled = compile_standard(
        {
            "language": "Solidity",
            "sources": {"ContratoBasico.sol": {"content": SOLIDITY_SRC}},
            "settings": {"outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}}}
        },
        solc_version="0.8.24",
    )
    status.update(label="Compilado ✔", state="complete")

abi = compiled["contracts"]["ContratoBasico.sol"]["ContratoBasico"]["abi"]
bytecode = compiled["contracts"]["ContratoBasico.sol"]["ContratoBasico"]["evm"]["bytecode"]["object"]

# -------------------- Conexión cadena --------------------
w3 = st.session_state.w3
cuentas = st.session_state.cuentas
vendedor = st.session_state.vendedor
comprador = st.session_state.comprador

st.sidebar.header("Cuentas simuladas")
st.sidebar.write(f"**Vendedor:** `{vendedor}`")
st.sidebar.write(f"**Comprador:** `{comprador}`")
st.sidebar.caption("Ambas con saldo de prueba en esta cadena simulada.")

# -------------------- Parámetros --------------------
st.subheader("Parámetros del contrato")
col1, col2, col3 = st.columns([1,1,1])
with col1:
    objeto = st.text_input("Objeto (texto libre)", value="Portátil X")
with col2:
    precio_eth = st.number_input("Precio (ETH)", value=0.01, min_value=0.0, step=0.005, format="%.5f")
with col3:
    plazo_min = st.number_input("Plazo (minutos)", value=60, min_value=1, step=5)

# asegurar fecha límite siempre futura (mínimo +120s)
now = int(time.time())
fecha_limite = now + max(120, int(plazo_min * 60))
precio_wei = Web3.to_wei(precio_eth, "ether")

# -------------------- Despliegue --------------------
if st.button("🚀 Desplegar contrato (vendedor)"):
    try:
        Contrato = w3.eth.contract(abi=abi, bytecode=bytecode)
        tx_hash = Contrato.constructor(comprador, objeto, precio_wei, fecha_limite).transact({"from": vendedor})
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        st.session_state.contract_addr = receipt.contractAddress
        push_event("Despliegue", f"Contrato en {receipt.contractAddress}", tx_hash)
        st.success(f"Contrato desplegado en: {st.session_state.contract_addr}")
    except Exception as e:
        st.error(f"Fallo al desplegar: {e}")

# --- Construcción segura del contrato ---
addr = st.session_state.contract_addr
if not addr:
    with st.container():
        st.info("Despliega el contrato para activar las acciones.")
        if st.button("♻️ Reiniciar entorno"):
            st.session_state.clear()
            boot_chain(force=True)
            st.success("Entorno reiniciado.")
            st.stop()
    st.stop()

# Confirmar que hay bytecode en esa dirección
code = w3.eth.get_code(addr)
if code in (b"", None) or len(code) == 0:
    st.error("El contrato no está desplegado en la dirección guardada. Reinicia y vuelve a desplegar.")
    if st.button("♻️ Reiniciar entorno"):
        st.session_state.clear(); st.rerun()
    st.stop()

contrato = w3.eth.contract(address=addr, abi=abi)

# -------------------- Lectura de estado (segura) --------------------
def leer_estado_seguro():
    try:
        est = contrato.functions.estado().call()
        obj = contrato.functions.objeto().call()
        ven = contrato.functions.vendedor().call()
        com = contrato.functions.comprador().call()
        precio = contrato.functions.precioWei().call()
        fecha = contrato.functions.fechaLimite().call()
        try:
            rest = contrato.functions.tiempoRestante().call()
        except Exception:
            rest = 0
        return est, obj, ven, com, precio, fecha, rest
    except Exception as e:
        st.error(f"No se pudo leer el contrato en {addr}. ¿Está desplegado? Detalle: {e}")
        st.stop()

def saldo(addr_):
    return Web3.from_wei(w3.eth.get_balance(addr_), "ether")

def saldo_contrato():
    return Web3.from_wei(w3.eth.get_balance(addr), "ether")

estados = ["Borrador", "Activo", "Resuelto", "Cancelado"]
est, obj, ven, com, precio, fecha, rest = leer_estado_seguro()

st.markdown("### Estado del contrato")
cA, cB, cC = st.columns(3)
with cA:
    st.metric("Estado", estados[est])
    st.metric("Objeto", obj)
with cB:
    st.metric("Precio (ETH)", float(Web3.from_wei(precio, "ether")))
    st.metric("Tiempo restante (s)", int(rest))
with cC:
    st.metric("Saldo contrato (ETH)", float(saldo_contrato()))
    st.metric("Plazo (epoch)", int(fecha))

st.markdown("### Saldos de las partes (ETH)")
c1, c2 = st.columns(2)
with c1:
    st.metric("Vendedor", float(saldo(ven)))
with c2:
    st.metric("Comprador", float(saldo(com)))

st.markdown("---")

# -------------------- Acciones --------------------
st.subheader("Acciones (máquina de estados)")
col = st.columns(4)

with col[0]:
    if st.button("✍️ Firmar (v/c)"):
        try:
            tx_hash = contrato.functions.firmar().transact({"from": vendedor})
            w3.eth.wait_for_transaction_receipt(tx_hash)
            push_event("Firmado", "Vendedor firma", tx_hash)
            st.success("Contrato firmado por vendedor.")
        except Exception as e:
            st.error(f"Error (vendedor): {e}")
        try:
            tx_hash = contrato.functions.firmar().transact({"from": comprador})
            w3.eth.wait_for_transaction_receipt(tx_hash)
            push_event("Firmado", "Comprador firma", tx_hash)
            st.success("Contrato firmado por comprador.")
        except Exception as e:
            st.warning(f"Info (comprador): {e}")

with col[1]:
    if st.button("💳 Pagar (comprador)"):
        try:
            tx_hash = contrato.functions.pagar().transact({"from": comprador, "value": precio_wei})
            w3.eth.wait_for_transaction_receipt(tx_hash)
            push_event("Pago", f"Comprador paga {precio_eth} ETH", tx_hash)
            st.success("Pago realizado por el comprador.")
        except Exception as e:
            st.error(f"Error en pago: {e}")

with col[2]:
    if st.button("✅ Confirmar entrega (comprador)"):
        try:
            tx_hash = contrato.functions.confirmarEntrega().transact({"from": comprador})
            w3.eth.wait_for_transaction_receipt(tx_hash)
            push_event("EntregaConfirmada", "Fondos liberados al vendedor", tx_hash)
            st.success("Entrega confirmada. Fondos liberados al vendedor.")
        except Exception as e:
            st.error(f"Error al confirmar: {e}")

with col[3]:
    if st.button("🛑 Cancelar (v/c)"):
        try:
            tx_hash = contrato.functions.cancelar().transact({"from": vendedor})
            w3.eth.wait_for_transaction_receipt(tx_hash)
            push_event("Cancelado", "Cancelación por vendedor (si procede)", tx_hash)
            st.success("Cancelación solicitada por vendedor (si procede).")
        except Exception as e:
            st.warning(f"Info (vendedor): {e}")
        try:
            tx_hash = contrato.functions.cancelar().transact({"from": comprador})
            w3.eth.wait_for_transaction_receipt(tx_hash)
            push_event("Cancelado", "Cancelación por comprador (si procede)", tx_hash)
            st.success("Cancelación solicitada por comprador (si procede).")
        except Exception as e:
            st.warning(f"Info (comprador): {e}")

# -------------------- Trazabilidad y descarga --------------------
st.markdown("### Trazabilidad (eventos)")
if st.session_state.event_log:
    for ev in reversed(st.session_state.event_log[-10:]):
        st.write(f"• **{ev['evento']}** — {ev['info']} — tx `{ev['tx'][:10]}…` — ts {ev['ts']}")
    # CSV de eventos
    csv_buf = io.StringIO()
    writer = csv.DictWriter(csv_buf, fieldnames=["ts","evento","info","tx"])
    writer.writeheader()
    for e in st.session_state.event_log:
        writer.writerow(e)
    st.download_button("⬇️ Descargar eventos (CSV)", data=csv_buf.getvalue(),
                       file_name="eventos_smart_contract.csv", mime="text/csv")
else:
    st.info("Aún no hay eventos. Ejecuta acciones para generarlos.")

# -------------------- Explicación didáctica --------------------
with st.expander("🧠 Mapa mental → formal → código (explicación)", expanded=False):
    st.markdown(
        """
**Cláusula 1 (Partes)** → `address vendedor/comprador`  
**Cláusula 2 (Objeto)** → `string objeto` (solo metadato; no asegura entrega física)  
**Cláusula 3 (Precio)** → `precioWei`; `pagar()` exige importe exacto (escrow en el contrato)  
**Cláusula 4 (Plazo)** → `fechaLimite` vs `block.timestamp`  
**Cláusula 5 (Flujo)** → Máquina de estados (`enum Estado`) y funciones `firmar/pagar/confirmarEntrega`  
**Cláusula 6 (Cancelación)** → `cancelar()` reembolsa al comprador si procede  
**Evidencia** → `event` + “saldo contrato” permiten auditar lo ocurrido
"""
    )

# -------------------- Reset del entorno --------------------
st.markdown("---")
col_reset = st.columns([1,1,1])
with col_reset[1]:
    if st.button("♻️ Reiniciar cadena y estado"):
        st.session_state.clear()
        boot_chain(force=True)
        st.success("Cadena y estado reiniciados.")
        st.rerun()

